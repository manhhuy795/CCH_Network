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
    from .policy_engine import (
        ICMP_ECHO_REPLY,
        ICMP_ECHO_REQUEST,
        POLICY_FLOW_PROFILES,
        PolicyEngine,
    )
    from scripts.network_model import (
        controlled_switches,
        controller_dpid_name_map,
        enforcement_switch_for_group,
        load_network_model,
    )
except ImportError:
    from policy_engine import (
        ICMP_ECHO_REPLY,
        ICMP_ECHO_REQUEST,
        POLICY_FLOW_PROFILES,
        PolicyEngine,
    )
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.network_model import (
        controlled_switches,
        controller_dpid_name_map,
        enforcement_switch_for_group,
        load_network_model,
    )


BASE_DIR = Path(__file__).resolve().parent
POLICY_FILE = Path(os.environ.get("SDN_POLICY_FILE", BASE_DIR / "policy.yml"))
RUNTIME_DIR = BASE_DIR / "runtime"
FLOWS_FILE = RUNTIME_DIR / "installed_flows.json"
EVENTS_FILE = RUNTIME_DIR / "events.jsonl"
ADMIN_SOCKET = Path(os.environ.get("CCH_OSKEN_ADMIN_SOCKET", "/tmp/cch_osken_admin.sock"))
ADMIN_TOKEN = os.environ.get("CCH_OSKEN_ADMIN_TOKEN", "cch-local-admin-token")

NETWORK_MODEL = load_network_model()
CONTROLLER_TARGETS = frozenset(controlled_switches(NETWORK_MODEL))
DPID_NAMES = controller_dpid_name_map(NETWORK_MODEL)
SWITCH_ROLES = {
    name: switch.get("role", "unknown")
    for name, switch in NETWORK_MODEL["switches"].items()
}
ENFORCEMENT_SWITCH_BY_GROUP = {
    group_name: enforcement_switch_for_group(NETWORK_MODEL, group_name)
    for group_name in NETWORK_MODEL["host_groups"]
}
POLICY_COOKIES = {
    policy_id: int(profile["cookie"])
    for policy_id, profile in POLICY_FLOW_PROFILES.items()
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

    @staticmethod
    def _flow_record_identity(entry: dict[str, Any]) -> tuple[Any, ...]:
        return (
            entry.get("switch"),
            entry.get("cookie"),
            entry.get("priority"),
            entry.get("match"),
        )

    @staticmethod
    def _write_event(payload: dict[str, Any]) -> None:
        with EVENTS_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _record(self, **entry: Any) -> None:
        payload = {"timestamp": utc_now(), **entry}
        identity = self._flow_record_identity(payload)
        self.installed_flows = [
            existing
            for existing in self.installed_flows
            if self._flow_record_identity(existing) != identity
        ]
        self.installed_flows.append(payload)
        self._write_flows()
        self._write_event(payload)

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
        cookie_label = f"0x{cookie:x}"
        self.installed_flows = [
            flow
            for flow in self.installed_flows
            if not (
                flow.get("switch") == switch_name
                and flow.get("cookie") == cookie_label
            )
        ]
        self._write_flows()
        self._write_event({
            "timestamp": utc_now(),
            "switch": switch_name,
            "switch_role": SWITCH_ROLES.get(switch_name, "unknown"),
            "priority": 0,
            "match": "cookie-delete",
            "action": "DELETE",
            "source": "*",
            "destination": "*",
            "reason": "Reload policy: xoa flow cu theo cookie.",
            "policy": "policy_reload",
            "cookie": cookie_label,
            "enforcement_switch": switch_name,
        })

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
        all_specs = self.policy.isolation_flow_specs()
        identities = self.policy.isolation_flow_identities()
        if len(identities) != len(set(identities)):
            raise RuntimeError("Policy isolation tao flow identity trung lap.")
        switch_specs = [spec for spec in all_specs if spec["switch"] == switch_name]
        if not switch_specs:
            self.logger.info(
                "Khong cai isolation DROP tren %s; access OVS chi transit/local switching.",
                switch_name,
            )
            return

        for spec in switch_specs:
            source_network = ipaddress.ip_network(spec["source_network"])
            destination_network = ipaddress.ip_network(spec["destination_network"])
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
                spec["priority"],
                match,
                [],
                {
                    "action": spec["action"],
                    "source": spec["source_network"],
                    "destination": spec["destination_network"],
                    "policy": spec["policy"],
                    "cookie": spec["cookie"],
                    "enforcement_switch": spec["switch"],
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

        it_policy = self.policy.policies.get("it_support_controlled_access") or {}
        managed_group_names = set(
            it_policy.get(
                "managed_user_groups",
                ["project_a", "project_b", "project_c", "telesale", "backoffice"],
            )
        )
        internal_destinations: list[tuple[str, str]] = [
            (name, str(network))
            for name, network in self.policy.networks.items()
            if name in managed_group_names
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
                    450,
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
                    460,
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
        switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
        voice_network = ipaddress.ip_network(f"{voice_service['ip']}/32")
        priority = (
            POLICY_FLOW_PROFILES["voice"]["priority"]
            if self.policy.policies.get("voice_flow_priority", False)
            else 350
        )

        managed_networks = [
            (group_name, user_network)
            for group_name, user_network in self.policy.networks.items()
            if ENFORCEMENT_SWITCH_BY_GROUP[group_name] == switch_name
        ]
        for group_name, user_network in managed_networks:
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
                        "enforcement_switch": switch_name,
                        "reason": "Voice duoc nhan dien va ap dung flow policy uu tien.",
                    },
                    idle_timeout=0,
                )

    def install_policy_flows(self, datapath) -> None:
        self.install_isolation_flows(datapath)
        self.install_voice_flows(datapath)
        self.install_it_support_flows(datapath)

    def install_arp_transit_flow(self, datapath) -> None:
        """Forward ARP locally so the first permitted IP test does not wait on Packet-In learning."""
        parser = datapath.ofproto_parser
        normal_port = getattr(datapath.ofproto, "OFPP_NORMAL", 0xFFFFFFFA)
        self.add_flow(
            datapath,
            100,
            parser.OFPMatch(eth_type=ether_types.ETH_TYPE_ARP),
            [parser.OFPActionOutput(normal_port)],
            {
                "action": "ALLOW",
                "reason": "Baseline ARP transit; khong bypass policy IPv4.",
            },
            idle_timeout=0,
        )

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        datapath = event.msg.datapath
        if datapath.id not in DPID_NAMES:
            self.logger.error(
                "Tu choi datapath ngoai controller target set: dpid=%016x",
                datapath.id,
            )
            return
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
        self.install_arp_transit_flow(datapath)
        self.install_policy_flows(datapath)
        self.logger.info("OVS %s đã kết nối, cài table-miss.", DPID_NAMES.get(datapath.id, datapath.id))

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        msg = event.msg
        datapath = msg.datapath
        if datapath.id not in DPID_NAMES:
            return
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
                        POLICY_FLOW_PROFILES["reactive_policy_drop"]["priority"],
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
                        self.add_flow(
                            datapath,
                            POLICY_FLOW_PROFILES["transit_to_enforcement"]["priority"],
                            match,
                            actions,
                            metadata,
                        )
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
