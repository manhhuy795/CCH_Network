#!/usr/bin/env python3
"""OS-Ken OpenFlow 1.3 controller cho SDN Edge Policy Call Center."""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import ipaddress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib.packet import ethernet, ether_types, icmp, ipv4, packet
from os_ken.ofproto import ofproto_v1_3

try:
    from .policy_engine import ICMP_ECHO_REPLY, ICMP_ECHO_REQUEST, PolicyEngine
    from scripts.network_model import dpid_name_map, load_network_model
except ImportError:
    from policy_engine import ICMP_ECHO_REPLY, ICMP_ECHO_REQUEST, PolicyEngine
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.network_model import dpid_name_map, load_network_model


BASE_DIR = Path(__file__).resolve().parent
POLICY_FILE = Path(os.environ.get("SDN_POLICY_FILE", BASE_DIR / "policy.yml"))
RUNTIME_DIR = BASE_DIR / "runtime"
FLOWS_FILE = RUNTIME_DIR / "installed_flows.json"
EVENTS_FILE = RUNTIME_DIR / "events.jsonl"
ADMIN_SOCKET = Path(os.environ.get("CCH_OSKEN_ADMIN_SOCKET", "/tmp/cch_osken_admin.sock"))
ADMIN_TOKEN = os.environ.get("CCH_OSKEN_ADMIN_TOKEN", "cch-local-admin-token")

NETWORK_MODEL = load_network_model()
DPID_NAMES = dpid_name_map(NETWORK_MODEL)
SWITCH_ROLES = {
    name: switch.get("role", "unknown")
    for name, switch in NETWORK_MODEL["switches"].items()
}
ENFORCEMENT_SWITCH_BY_GROUP = {
    group_name: ("dist_branch" if group["site"] == "Branch" else "core_hq")
    for group_name, group in NETWORK_MODEL["host_groups"].items()
}
POLICY_COOKIES = {
    "hq_project_isolation": 0x1001,
    "branch_isolation": 0x1002,
    "hq_social_block": 0x1003,
    "branch_social_block": 0x1004,
    "allowed_services": 0x1100,
    "voice": 0x1200,
    "it_support": 0x1300,
    "it_support_return": 0x1301,
    "it_inbound_block": 0x1302,
    "reactive_policy_drop": 0x1000,
    "transit_to_enforcement": 0x1100,
    "internet_inbound_block": 0x1100,
    "runtime": 0x0000,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CallCenterPolicyController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        self.policy = PolicyEngine(POLICY_FILE)
        self.mac_to_port: dict[int, dict[str, int]] = {}
        self.datapaths: dict[int, Any] = {}
        self.installed_flows: list[dict[str, Any]] = []
        self.file_lock = threading.Lock()
        self._write_flows()
        self._start_admin_socket()
        self.logger.info("Đã nạp policy SDN từ %s", POLICY_FILE)

    def _write_flows(self) -> None:
        with self.file_lock:
            temp_file = FLOWS_FILE.with_suffix(".tmp")
            temp_file.write_text(
                json.dumps(self.installed_flows[-2000:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_file.replace(FLOWS_FILE)

    def _record(self, **entry: Any) -> None:
        payload = {"timestamp": utc_now(), **entry}
        self.installed_flows.append(payload)
        self._write_flows()
        with EVENTS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _start_admin_socket(self) -> None:
        if not hasattr(socket, "AF_UNIX"):
            self.logger.warning("Unix Domain Socket khong kha dung; bo qua controller admin interface.")
            return
        thread = threading.Thread(target=self._admin_socket_loop, name="cch-osken-admin", daemon=True)
        thread.start()

    def _admin_socket_loop(self) -> None:
        try:
            if ADMIN_SOCKET.exists():
                ADMIN_SOCKET.unlink()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(ADMIN_SOCKET))
            ADMIN_SOCKET.chmod(0o600)
            server.listen(5)
        except OSError as exc:
            self.logger.error("Khong mo duoc admin socket %s: %s", ADMIN_SOCKET, exc)
            return

        self.logger.info("Controller admin socket dang lang nghe tai %s", ADMIN_SOCKET)
        while True:
            connection, _addr = server.accept()
            with connection:
                try:
                    request = json.loads(connection.recv(65536).decode("utf-8"))
                    response = self._handle_admin_request(request)
                except Exception as exc:  # noqa: BLE001
                    response = {"ok": False, "message": f"Loi controller admin: {exc}"}
                connection.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))

    def _handle_admin_request(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("token") != ADMIN_TOKEN:
            return {"ok": False, "message": "Token noi bo khong hop le."}
        if request.get("action") != "reload_policy":
            return {"ok": False, "message": "Lenh admin khong duoc ho tro."}
        return self.reload_policy()

    def _delete_cookie(self, datapath, cookie: int) -> None:
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        datapath.send_msg(
            parser.OFPFlowMod(
                datapath=datapath,
                command=ofproto.OFPFC_DELETE,
                cookie=cookie,
                cookie_mask=0xFFFFFFFFFFFFFFFF,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY,
                match=parser.OFPMatch(),
            )
        )
        switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
        self._record(
            switch=switch_name,
            switch_role=SWITCH_ROLES.get(switch_name, "unknown"),
            priority=0,
            match="cookie-delete",
            action="DELETE",
            source="*",
            destination="*",
            reason="Reload policy: xoa flow cu theo cookie.",
            policy="policy_reload",
            cookie=f"0x{cookie:x}",
            enforcement_switch=switch_name,
        )

    def reload_policy(self) -> dict[str, Any]:
        old_policies = dict(self.policy.policies)
        new_policy = PolicyEngine(POLICY_FILE)
        changed = [
            key for key, value in new_policy.policies.items()
            if old_policies.get(key) != value
        ]
        cookies = sorted({
            value for key, value in POLICY_COOKIES.items()
            if key not in {"runtime"} and value
        })
        flows_removed = 0
        for datapath in list(self.datapaths.values()):
            for cookie in cookies:
                self._delete_cookie(datapath, cookie)
                flows_removed += 1

        self.policy = new_policy
        before = len(self.installed_flows)
        updated_switches: list[str] = []
        for datapath in list(self.datapaths.values()):
            switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
            self.install_policy_flows(datapath)
            updated_switches.append(switch_name)
        flows_installed = max(0, len(self.installed_flows) - before)
        return {
            "ok": True,
            "message": "Policy da reload va reconcile OpenFlow theo cookie.",
            "policies_reloaded": len(changed),
            "flows_removed": flows_removed,
            "flows_installed": flows_installed,
            "switches_updated": sorted(updated_switches),
        }

    def add_flow(self, datapath, priority, match, actions, metadata, idle_timeout=180, hard_timeout=0):
        parser = datapath.ofproto_parser
        policy_id = metadata.get("policy", "runtime")
        cookie = int(metadata.get("cookie", POLICY_COOKIES.get(policy_id, 0)))
        instructions = [
            parser.OFPInstructionActions(
                datapath.ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ] if actions else []
        datapath.send_msg(
            parser.OFPFlowMod(
                datapath=datapath,
                cookie=cookie,
                priority=priority,
                match=match,
                instructions=instructions,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout,
            )
        )
        switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
        self._record(
            switch=switch_name,
            switch_role=SWITCH_ROLES.get(switch_name, "unknown"),
            priority=priority,
            match=str(match),
            action=metadata["action"],
            source=metadata.get("source", "*"),
            destination=metadata.get("destination", "*"),
            reason=metadata["reason"],
            policy=policy_id,
            cookie=f"0x{cookie:x}",
            enforcement_switch=metadata.get("enforcement_switch", switch_name),
        )
        if metadata.get("policy"):
            self.logger.info(
                "POLICY INSTALLED switch=%s role=%s policy=%s priority=%s",
                switch_name,
                SWITCH_ROLES.get(switch_name, "unknown"),
                metadata["policy"],
                priority,
            )

    def install_isolation_flows(self, datapath):
        """Cài DROP chủ động để segmentation không phụ thuộc gói Packet-In đầu tiên."""
        parser = datapath.ofproto_parser
        switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
        if switch_name == "core_hq" and self.policy.policies["isolate_hq_projects"]:
            isolation_pairs = (
                ("project_a", "project_b", "hq_project_isolation"),
                ("project_a", "project_c", "hq_project_isolation"),
                ("project_b", "project_c", "hq_project_isolation"),
            )
        elif switch_name == "dist_branch" and self.policy.policies["isolate_branch_vlan_50_60"]:
            isolation_pairs = (("telesale", "backoffice", "branch_isolation"),)
        else:
            self.logger.info("Khong cai isolation DROP tren %s; access OVS chi transit/local switching.", switch_name)
            return

        for left_group, right_group, policy_id in isolation_pairs:
            left_network = self.policy.networks[left_group]
            right_network = self.policy.networks[right_group]
            for source_network, destination_network in (
                (left_network, right_network),
                (right_network, left_network),
            ):
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(
                        str(source_network.network_address),
                        str(source_network.netmask),
                    ),
                    ipv4_dst=(
                        str(destination_network.network_address),
                        str(destination_network.netmask),
                    ),
                )
                self.add_flow(
                    datapath,
                    400,
                    match,
                    [],
                    {
                        "action": "DROP",
                        "source": str(source_network),
                        "destination": str(destination_network),
                        "policy": policy_id,
                        "enforcement_switch": switch_name,
                        "reason": "Cách ly VLAN chủ động tại SDN Edge.",
                    },
                    idle_timeout=0,
                )
        self.logger.info("Đã cài isolation flow chủ động priority 400 trên %s.", switch_name)

    def install_it_support_flows(self, datapath):
        """Cài ALLOW chủ động cho VLAN IT để remote/support đi ổn định qua mọi OVS."""
        if not self.policy.policies.get("allow_it_support_controlled_access", False):
            return

        parser = datapath.ofproto_parser
        normal_port = getattr(datapath.ofproto, "OFPP_NORMAL", 0xFFFFFFFA)
        normal_actions = [parser.OFPActionOutput(normal_port)]
        switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
        if switch_name != "core_hq":
            self.logger.info("Khong cai IT Support policy tren %s; core_hq la enforcement point.", switch_name)
            return

        it_network = self.policy.networks.get("it_support")
        if not it_network:
            return

        internal_destinations: list[tuple[str, str]] = [
            (name, str(network))
            for name, network in self.policy.networks.items()
            if name != "it_support"
        ]
        allowed_services = set(self.policy.policies.get("it_support_allowed_services", ["h90", "hzalo", "hcall"]))
        service_destinations: list[tuple[str, str]] = [
            (name, f"{service['ip']}/32")
            for name, service in self.policy.services.items()
            if "ip" in service and name in allowed_services
        ]

        for destination_name, destination_prefix in internal_destinations:
            destination_network = ipaddress.ip_network(destination_prefix)
            for source_network, target_network, source_label, target_label in (
                (it_network, destination_network, "it_support", destination_name),
            ):
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=1,
                    icmpv4_type=ICMP_ECHO_REQUEST,
                    ipv4_src=(str(source_network.network_address), str(source_network.netmask)),
                    ipv4_dst=(str(target_network.network_address), str(target_network.netmask)),
                )
                self.add_flow(
                    datapath,
                    450,
                    match,
                    normal_actions,
                    {
                        "action": "ALLOW",
                        "source": source_label,
                        "destination": target_label,
                        "policy": "it_support",
                        "enforcement_switch": switch_name,
                        "reason": "IT Support chi duoc khoi tao ICMP echo-request de remote/support co kiem soat.",
                    },
                    idle_timeout=0,
                )
                return_match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=1,
                    icmpv4_type=ICMP_ECHO_REPLY,
                    ipv4_src=(str(target_network.network_address), str(target_network.netmask)),
                    ipv4_dst=(str(source_network.network_address), str(source_network.netmask)),
                )
                self.add_flow(
                    datapath,
                    445,
                    return_match,
                    normal_actions,
                    {
                        "action": "ALLOW",
                        "source": target_label,
                        "destination": source_label,
                        "policy": "it_support_return",
                        "enforcement_switch": switch_name,
                        "reason": "Chi cho phep ICMP echo-reply ve IT cho phien IT khoi tao.",
                    },
                    idle_timeout=0,
                )
                inbound_request_match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=1,
                    icmpv4_type=ICMP_ECHO_REQUEST,
                    ipv4_src=(str(target_network.network_address), str(target_network.netmask)),
                    ipv4_dst=(str(source_network.network_address), str(source_network.netmask)),
                )
                self.add_flow(
                    datapath,
                    455,
                    inbound_request_match,
                    [],
                    {
                        "action": "DROP",
                        "source": target_label,
                        "destination": source_label,
                        "policy": "it_inbound_block",
                        "enforcement_switch": switch_name,
                        "reason": "User thuong khong duoc chu dong ping vao VLAN IT Support.",
                    },
                    idle_timeout=0,
                )

        for destination_name, destination_prefix in service_destinations:
            destination_network = ipaddress.ip_network(destination_prefix)
            for source_network, target_network, source_label, target_label in (
                (it_network, destination_network, "it_support", destination_name),
            ):
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=1,
                    icmpv4_type=ICMP_ECHO_REQUEST,
                    ipv4_src=(str(source_network.network_address), str(source_network.netmask)),
                    ipv4_dst=(str(target_network.network_address), str(target_network.netmask)),
                )
                self.add_flow(
                    datapath,
                    450,
                    match,
                    normal_actions,
                    {
                        "action": "ALLOW",
                        "source": source_label,
                        "destination": target_label,
                        "policy": "it_support",
                        "enforcement_switch": switch_name,
                        "reason": "IT Support chi duoc ping kiem tra dich vu quan tri duoc khai bao.",
                    },
                    idle_timeout=0,
                )
                return_match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=1,
                    icmpv4_type=ICMP_ECHO_REPLY,
                    ipv4_src=(str(target_network.network_address), str(target_network.netmask)),
                    ipv4_dst=(str(source_network.network_address), str(source_network.netmask)),
                )
                self.add_flow(
                    datapath,
                    445,
                    return_match,
                    normal_actions,
                    {
                        "action": "ALLOW",
                        "source": target_label,
                        "destination": source_label,
                        "policy": "it_support_return",
                        "enforcement_switch": switch_name,
                        "reason": "Chi cho phep ICMP echo-reply ve IT cho phien IT khoi tao.",
                    },
                    idle_timeout=0,
                )

        social = self.policy.services.get("hsocial", {})
        if self.policy.policies.get("block_social_media", False) and "ip" in social:
            social_network = ipaddress.ip_network(f"{social['ip']}/32")
            for source_network, target_network, source_label, target_label in (
                (it_network, social_network, "it_support", "hsocial"),
                (social_network, it_network, "hsocial", "it_support"),
            ):
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(source_network.network_address), str(source_network.netmask)),
                    ipv4_dst=(str(target_network.network_address), str(target_network.netmask)),
                )
                self.add_flow(
                    datapath,
                    460,
                    match,
                    [],
                    {
                        "action": "DROP",
                        "source": source_label,
                        "destination": target_label,
                        "policy": "hq_social_block",
                        "enforcement_switch": switch_name,
                        "reason": "Block Social Media ca IT Support; IT management khong duoc bypass social policy.",
                    },
                    idle_timeout=0,
                )

    def install_voice_flows(self, datapath):
        """Cai ALLOW chu dong hai chieu cho PBX/SBC Voice reachability; day chua phai QoS hoan chinh."""
        if not self.policy.policies.get("allow_voice", False):
            return

        voice_service = self.policy.services.get("h90")
        if not voice_service or "ip" not in voice_service:
            return

        parser = datapath.ofproto_parser
        normal_port = getattr(datapath.ofproto, "OFPP_NORMAL", 0xFFFFFFFA)
        normal_actions = [parser.OFPActionOutput(normal_port)]
        voice_network = ipaddress.ip_network(f"{voice_service['ip']}/32")
        priority = 425 if self.policy.policies.get("voice_flow_priority", False) else 350

        for group_name, user_network in self.policy.networks.items():
            for source_network, target_network, source_label, target_label in (
                (user_network, voice_network, group_name, "h90"),
                (voice_network, user_network, "h90", group_name),
            ):
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(source_network.network_address), str(source_network.netmask)),
                    ipv4_dst=(str(target_network.network_address), str(target_network.netmask)),
                )
                self.add_flow(
                    datapath,
                    priority,
                    match,
                    normal_actions,
                    {
                        "action": "ALLOW",
                        "source": source_label,
                        "destination": target_label,
                        "policy": "voice",
                        "enforcement_switch": DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}"),
                        "reason": "Voice duoc nhan dien va ap dung flow policy uu tien.",
                    },
                    idle_timeout=0,
                )

    def install_service_policy_flows(self, datapath):
        """Cài flow chủ động cho Internet services để kết quả ping khớp policy ổn định."""
        parser = datapath.ofproto_parser
        normal_port = getattr(datapath.ofproto, "OFPP_NORMAL", 0xFFFFFFFA)
        normal_actions = [parser.OFPActionOutput(normal_port)]
        switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
        user_networks = [
            (name, network)
            for name, network in self.policy.networks.items()
            if name != "it_support"
        ]
        allowed_service_names = []
        if self.policy.policies.get("allow_zalo", False):
            allowed_service_names.append("hzalo")
        if self.policy.policies.get("allow_call_app", False):
            allowed_service_names.append("hcall")
        if self.policy.policies.get("allow_general_internet", False):
            allowed_service_names.append("hinternet")

        for service_name in allowed_service_names:
            service = self.policy.services.get(service_name, {})
            if "ip" not in service:
                continue
            service_network = ipaddress.ip_network(f"{service['ip']}/32")
            for group_name, user_network in user_networks:
                for source_network, target_network, source_label, target_label in (
                    (user_network, service_network, group_name, service_name),
                    (service_network, user_network, service_name, group_name),
                ):
                    match = parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ipv4_src=(str(source_network.network_address), str(source_network.netmask)),
                        ipv4_dst=(str(target_network.network_address), str(target_network.netmask)),
                    )
                    self.add_flow(
                        datapath,
                        330,
                        match,
                        normal_actions,
                        {
                            "action": "ALLOW",
                            "source": source_label,
                            "destination": target_label,
                            "policy": "allowed_services",
                            "enforcement_switch": switch_name,
                            "reason": "Service duoc policy cho phep; return traffic duoc chap nhan.",
                        },
                        idle_timeout=0,
                    )
                echo_request_match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=1,
                    icmpv4_type=ICMP_ECHO_REQUEST,
                    ipv4_src=(str(service_network.network_address), str(service_network.netmask)),
                    ipv4_dst=(str(user_network.network_address), str(user_network.netmask)),
                )
                if switch_name == ENFORCEMENT_SWITCH_BY_GROUP[group_name]:
                    self.add_flow(
                        datapath,
                        385,
                        echo_request_match,
                        [],
                        {
                            "action": "DROP",
                            "source": service_name,
                            "destination": group_name,
                            "policy": "internet_inbound_block",
                            "enforcement_switch": switch_name,
                            "reason": "Chan ping chu dong tu Internet/service vao user noi bo.",
                        },
                        idle_timeout=0,
                    )

        social = self.policy.services.get("hsocial", {})
        if self.policy.policies.get("block_social_media", False) and "ip" in social:
            social_network = ipaddress.ip_network(f"{social['ip']}/32")
            for group_name, user_network in user_networks:
                for source_network, target_network, source_label, target_label in (
                    (user_network, social_network, group_name, "hsocial"),
                    (social_network, user_network, "hsocial", group_name),
                ):
                    match = parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ipv4_src=(str(source_network.network_address), str(source_network.netmask)),
                        ipv4_dst=(str(target_network.network_address), str(target_network.netmask)),
                    )
                    if switch_name == ENFORCEMENT_SWITCH_BY_GROUP[group_name]:
                        self.add_flow(
                            datapath,
                            390,
                            match,
                            [],
                            {
                                "action": "DROP",
                                "source": source_label,
                                "destination": target_label,
                                "policy": "branch_social_block" if switch_name == "dist_branch" else "hq_social_block",
                                "enforcement_switch": switch_name,
                                "reason": "Block Social Media cho user thuong.",
                            },
                            idle_timeout=0,
                        )

    def install_policy_flows(self, datapath) -> None:
        self.install_isolation_flows(datapath)
        self.install_service_policy_flows(datapath)
        self.install_voice_flows(datapath)
        self.install_it_support_flows(datapath)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        datapath = event.msg.datapath
        self.datapaths[datapath.id] = datapath
        parser = datapath.ofproto_parser
        actions = [
            parser.OFPActionOutput(
                datapath.ofproto.OFPP_CONTROLLER,
                datapath.ofproto.OFPCML_NO_BUFFER,
            )
        ]
        self.add_flow(
            datapath,
            0,
            parser.OFPMatch(),
            actions,
            {"action": "PACKET_IN", "reason": "Table-miss gửi gói đầu tiên lên controller."},
            idle_timeout=0,
        )
        self.install_policy_flows(datapath)
        self.logger.info("OVS %s đã kết nối, cài table-miss.", DPID_NAMES.get(datapath.id, datapath.id))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        msg = event.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if not eth or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})[eth.src] = in_port
        out_port = self.mac_to_port[dpid].get(eth.dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        ip_packet = pkt.get_protocol(ipv4.ipv4)
        icmp_packet = pkt.get_protocol(icmp.icmp)
        icmp_type = icmp_packet.type if icmp_packet else None

        if ip_packet:
            decision = self.policy.decide_ip(ip_packet.src, ip_packet.dst, icmp_type=icmp_type)
            match_fields = {
                "eth_type": ether_types.ETH_TYPE_IP,
                "ipv4_src": ip_packet.src,
                "ipv4_dst": ip_packet.dst,
            }
            if icmp_type is not None:
                match_fields["ip_proto"] = 1
                match_fields["icmpv4_type"] = icmp_type
            match = parser.OFPMatch(**match_fields)
            metadata = {
                "action": decision["action"].upper(),
                "source": ip_packet.src,
                "destination": ip_packet.dst,
                "reason": decision["reason"],
            }
            if decision["action"] == "deny":
                switch_name = DPID_NAMES.get(dpid, f"dpid-{dpid}")
                if switch_name == decision.get("blocked_at"):
                    self.add_flow(
                        datapath,
                        300,
                        match,
                        [],
                        {
                            **metadata,
                            "policy": "reactive_policy_drop",
                            "enforcement_switch": switch_name,
                        },
                    )
                else:
                    metadata = {
                        **metadata,
                        "action": "ALLOW",
                        "policy": "transit_to_enforcement",
                        "enforcement_switch": decision.get("blocked_at"),
                        "reason": f"Transit toi enforcement switch {decision.get('blocked_at')}; khong DROP tai {switch_name}.",
                    }
                    if out_port != ofproto.OFPP_FLOOD:
                        self.add_flow(datapath, 180, match, actions, metadata)
                    return
                self.logger.info(
                    "CHẶN %s -> %s tại %s: %s",
                    ip_packet.src,
                    ip_packet.dst,
                    DPID_NAMES.get(dpid, dpid),
                    decision["reason"],
                )
                return

            if out_port != ofproto.OFPP_FLOOD:
                priority = 250 if decision.get("voice_flow_priority") else 200
                self.add_flow(datapath, priority, match, actions, metadata)
                if decision.get("voice_flow_priority"):
                    self.logger.info("VOICE FLOW PRIORITY INSTALLED: %s -> %s", ip_packet.src, ip_packet.dst)
                else:
                    self.logger.info("CHO PHÉP %s -> %s: %s", ip_packet.src, ip_packet.dst, decision["reason"])
        elif eth.ethertype == ether_types.ETH_TYPE_ARP and out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_type=ether_types.ETH_TYPE_ARP,
                eth_dst=eth.dst,
            )
            self.add_flow(
                datapath,
                50,
                match,
                actions,
                {"action": "ALLOW", "reason": "Học MAC chỉ cho ARP, không bypass IP policy."},
                idle_timeout=120,
            )

        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data,
            )
        )
