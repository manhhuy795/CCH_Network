#!/usr/bin/env python3
"""OS-Ken OpenFlow 1.3 controller cho SDN Edge Policy Call Center."""

from __future__ import annotations

import json
import logging
import os
import threading
import ipaddress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib.packet import ethernet, ether_types, ipv4, packet
from os_ken.ofproto import ofproto_v1_3

try:
    from .policy_engine import PolicyEngine
except ImportError:
    from policy_engine import PolicyEngine


BASE_DIR = Path(__file__).resolve().parent
POLICY_FILE = Path(os.environ.get("SDN_POLICY_FILE", BASE_DIR / "policy.yml"))
RUNTIME_DIR = BASE_DIR / "runtime"
FLOWS_FILE = RUNTIME_DIR / "installed_flows.json"
EVENTS_FILE = RUNTIME_DIR / "events.jsonl"

DPID_NAMES = {
    1: "access_hq_a",
    2: "access_hq_b",
    3: "access_hq_c",
    4: "voice_mgmt",
    5: "core_hq",
    6: "access_branch",
    7: "dist_branch",
    8: "access_hq_it",
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
        self.installed_flows: list[dict[str, Any]] = []
        self.file_lock = threading.Lock()
        self._write_flows()
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

    def add_flow(self, datapath, priority, match, actions, metadata, idle_timeout=180):
        parser = datapath.ofproto_parser
        instructions = [
            parser.OFPInstructionActions(
                datapath.ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ] if actions else []
        datapath.send_msg(
            parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=instructions,
                idle_timeout=idle_timeout,
            )
        )
        self._record(
            switch=DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}"),
            priority=priority,
            match=str(match),
            action=metadata["action"],
            source=metadata.get("source", "*"),
            destination=metadata.get("destination", "*"),
            reason=metadata["reason"],
        )

    def install_isolation_flows(self, datapath):
        """Cài DROP chủ động để segmentation không phụ thuộc gói Packet-In đầu tiên."""
        parser = datapath.ofproto_parser
        switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
        hq_pairs = (
            ("project_a", "project_b"),
            ("project_a", "project_c"),
            ("project_b", "project_c"),
        )
        isolation_pairs = (
            list(hq_pairs)
            if self.policy.policies["isolate_hq_projects"]
            else []
        )
        if self.policy.policies["isolate_branch_vlan_50_60"]:
            isolation_pairs.append(("telesale", "backoffice"))

        for left_group, right_group in isolation_pairs:
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
                        "reason": "Cách ly VLAN chủ động tại SDN Edge.",
                    },
                    idle_timeout=0,
                )
        self.logger.info("Đã cài isolation flow chủ động priority 400 trên %s.", switch_name)

    def install_it_support_flows(self, datapath):
        """Cài ALLOW chủ động cho VLAN IT để remote/support đi ổn định qua mọi OVS."""
        if not self.policy.policies.get("allow_it_support_full_access", False):
            return

        parser = datapath.ofproto_parser
        normal_port = getattr(datapath.ofproto, "OFPP_NORMAL", 0xFFFFFFFA)
        normal_actions = [parser.OFPActionOutput(normal_port)]
        it_network = self.policy.networks.get("it_support")
        if not it_network:
            return

        destinations: list[tuple[str, str]] = [
            (name, str(network))
            for name, network in self.policy.networks.items()
            if name != "it_support"
        ]
        destinations.extend(
            (name, f"{service['ip']}/32")
            for name, service in self.policy.services.items()
            if "ip" in service
        )

        for destination_name, destination_prefix in destinations:
            destination_network = ipaddress.ip_network(destination_prefix)
            for source_network, target_network, source_label, target_label in (
                (it_network, destination_network, "it_support", destination_name),
                (destination_network, it_network, destination_name, "it_support"),
            ):
                match = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
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
                        "reason": "IT Support full access: remote/helpdesk được ưu tiên cho phép.",
                    },
                    idle_timeout=0,
                )

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        datapath = event.msg.datapath
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
        self.install_isolation_flows(datapath)
        self.install_it_support_flows(datapath)
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

        if ip_packet:
            decision = self.policy.decide_ip(ip_packet.src, ip_packet.dst)
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=ip_packet.src,
                ipv4_dst=ip_packet.dst,
            )
            metadata = {
                "action": decision["action"].upper(),
                "source": ip_packet.src,
                "destination": ip_packet.dst,
                "reason": decision["reason"],
            }
            if decision["action"] == "deny":
                self.add_flow(datapath, 300, match, [], metadata)
                self.logger.info(
                    "CHẶN %s -> %s tại %s: %s",
                    ip_packet.src,
                    ip_packet.dst,
                    DPID_NAMES.get(dpid, dpid),
                    decision["reason"],
                )
                return

            if out_port != ofproto.OFPP_FLOOD:
                priority = 250 if decision.get("voice_priority") else 200
                self.add_flow(datapath, priority, match, actions, metadata)
                if decision.get("voice_priority"):
                    self.logger.info("VOICE PRIORITY FLOW INSTALLED: %s -> %s", ip_packet.src, ip_packet.dst)
                else:
                    self.logger.info("CHO PHÉP %s -> %s: %s", ip_packet.src, ip_packet.dst, decision["reason"])
        elif out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=eth.dst)
            self.add_flow(
                datapath,
                50,
                match,
                actions,
                {"action": "ALLOW", "reason": "Học MAC cho ARP/L2."},
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
