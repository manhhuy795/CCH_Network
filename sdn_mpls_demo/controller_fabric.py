#!/usr/bin/env python3
"""OS-Ken OpenFlow 1.3 Full-SDN Fabric Controller for CCH Enterprise Network.

This controller completely replaces traditional OFPP_NORMAL forwarding within
the 6-switch enterprise OVS fabric:
  - access_floor1 (dpid 0x0001)
  - access_floor2 (dpid 0x0002)
  - core_hq (dpid 0x0003)
  - access_branch (dpid 0x0004)
  - dist_branch (dpid 0x0005)
  - infra_access (dpid 0x0006)

Boundary Rule:
  Firewalls (fw_hq, fw_telesale), CEs, provider MPLS L2VPN, and IPsec tunnel
  abstractions remain outside the SDN domain.

OpenFlow 1.3 Multi-Table Pipeline:
  Table 0:  Ingress classification, port-VLAN validation & anti-spoofing
  Table 10: Protocol validation & ARP handling (Proxy ARP)
  Table 20: Security Policy (Project isolation, Guest, IoT, IT Support, Voice, Services)
  Table 30: Forwarding & Routing Engine (L2 explicit output, L3 MAC rewrite & TTL dec)
  Table 40: Egress & QoS (Voice flow prioritization, explicit port output)

CRITICAL REQUIREMENT:
  Zero usage of OFPP_NORMAL. Every packet forwarding decision is programmed
  with explicit OpenFlow 1.3 output actions.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
import socket
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from os_ken.base import app_manager
    from os_ken.controller import ofp_event
    from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from os_ken.lib.packet import (
        arp,
        ether_types,
        ethernet,
        icmp,
        ipv4,
        packet,
        tcp,
        udp,
        vlan,
    )
    from os_ken.ofproto import ofproto_v1_3
except ImportError:
    # Graceful mock for offline / Windows unit-test portability
    class _MockAppManager:
        class OSKenApp:
            def __init__(self, *args, **kwargs) -> None:
                self.logger = logging.getLogger("cch.fabric")

    class _MockOfprotoV13:
        OFP_VERSION = 4
        OFPVID_PRESENT = 0x1000
        OFPVID_NONE = 0x0000
        OFPP_CONTROLLER = 0xFFFFFFFD
        OFPP_MAX = 0xFFFFFF00
        OFPCML_NO_BUFFER = 0xFFFF
        OFP_NO_BUFFER = 0xFFFFFFFF
        OFPTT_ALL = 0xFF
        OFPFC_DELETE = 3
        OFPP_ANY = 0xFFFFFFFF
        OFPG_ANY = 0xFFFFFFFF
        OFPPS_LINK_DOWN = 1
        OFPIT_APPLY_ACTIONS = 4

    class _MockEtherTypes:
        ETH_TYPE_IP = 0x0800
        ETH_TYPE_ARP = 0x0806
        ETH_TYPE_LLDP = 0x88CC

    class _MockOfpEvent:
        EventOFPSwitchFeatures = "EventOFPSwitchFeatures"
        EventOFPPortDescStatsReply = "EventOFPPortDescStatsReply"
        EventOFPPacketIn = "EventOFPPacketIn"
        EventOFPPortStatus = "EventOFPPortStatus"

    app_manager = _MockAppManager()
    ofp_event = _MockOfpEvent()
    CONFIG_DISPATCHER = "config"
    MAIN_DISPATCHER = "main"

    def set_ev_cls(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    ofproto_v1_3 = _MockOfprotoV13()
    ether_types = _MockEtherTypes()
    arp = Any
    ethernet = Any
    icmp = Any
    ipv4 = Any
    packet = Any
    tcp = Any
    udp = Any
    vlan = Any

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
        build_host_inventory,
    )
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sdn_mpls_demo.policy_engine import (
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
        build_host_inventory,
    )

BASE_DIR = Path(__file__).resolve().parent
POLICY_FILE = Path(os.environ.get("SDN_POLICY_FILE", BASE_DIR / "policy.yml"))
RUNTIME_DIR = BASE_DIR / "runtime"
FLOWS_FILE = RUNTIME_DIR / "installed_flows.json"
FABRIC_FLOWS_FILE = RUNTIME_DIR / "fabric_flows.json"
FABRIC_STATE_FILE = RUNTIME_DIR / "fabric_state.json"
EVENTS_FILE = RUNTIME_DIR / "events.jsonl"
ADMIN_SOCKET = Path(os.environ.get("CCH_OSKEN_ADMIN_SOCKET", "/tmp/cch_osken_admin.sock"))
ADMIN_TOKEN = os.environ.get("CCH_OSKEN_ADMIN_TOKEN", "cch-local-admin-token")

# OpenFlow Multi-Table IDs
TABLE_INGRESS_FILTER = 0
TABLE_PROTO_VALIDATION = 10
TABLE_SECURITY_POLICY = 20
TABLE_FORWARDING = 30
TABLE_EGRESS_QOS = 40

# Virtual Gateways
GATEWAY_MAC_HQ = "00:00:5e:00:01:01"
GATEWAY_MAC_BRANCH = "00:00:5e:00:02:01"

GATEWAY_IPS_HQ = {
    "10.10.93.1",
    "10.10.100.1",
    "10.10.101.1",
    "10.10.103.1",
    "10.10.104.1",
    "10.10.110.1",
    "10.10.120.1",
    "10.10.140.1",
}
GATEWAY_IPS_BRANCH = {
    "10.20.50.1",
}
ALL_GATEWAY_IPS = GATEWAY_IPS_HQ | GATEWAY_IPS_BRANCH

# VLAN Metadata
VLAN_SUBNETS = {
    93: "10.10.93.0/24",
    100: "10.10.100.0/24",
    101: "10.10.101.0/24",
    103: "10.10.103.0/24",
    104: "10.10.104.0/24",
    110: "10.10.110.0/24",
    120: "10.10.120.0/24",
    140: "10.10.140.0/24",
    50: "10.20.50.0/24",
}

PROJECT_VLANS = {93, 101, 103, 104}

NETWORK_MODEL = load_network_model()
CONTROLLER_TARGETS = frozenset(controlled_switches(NETWORK_MODEL))
DPID_NAMES = controller_dpid_name_map(NETWORK_MODEL)
NAME_DPIDS = {name: dpid for dpid, name in DPID_NAMES.items()}
SWITCH_ROLES = {
    name: switch.get("role", "unknown")
    for name, switch in NETWORK_MODEL["switches"].items()
}

POLICY_COOKIES = {
    policy_id: int(profile["cookie"])
    for policy_id, profile in POLICY_FLOW_PROFILES.items()
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FabricTopology:
    """Graph representation of the 6-switch enterprise fabric for shortest path."""

    def __init__(self) -> None:
        self.switches: set[str] = set(DPID_NAMES.values())
        # (u, v) -> {"local_port": int, "remote_port": int, "status": "up"|"down", "vlans": set[int]}
        self.links: dict[tuple[str, str], dict[str, Any]] = {}
        self.port_to_neighbor: dict[tuple[str, int], tuple[str, int]] = {}
        self.switch_ports: dict[str, dict[int, str]] = defaultdict(dict)  # switch -> {port_no: port_name}
        self.port_name_to_no: dict[str, dict[str, int]] = defaultdict(dict)

    def register_port(self, switch: str, port_no: int, port_name: str) -> None:
        self.switch_ports[switch][port_no] = port_name
        self.port_name_to_no[switch][port_name] = port_no

    def add_link(
        self,
        u: str,
        v: str,
        local_port: int,
        remote_port: int,
        vlans: set[int] | None = None,
        status: str = "up",
    ) -> None:
        link_info = {
            "local_port": local_port,
            "remote_port": remote_port,
            "status": status,
            "vlans": vlans or set(VLAN_SUBNETS.keys()),
        }
        self.links[(u, v)] = link_info
        self.port_to_neighbor[(u, local_port)] = (v, remote_port)

    def set_link_status(self, u: str, v: str, status: str) -> None:
        if (u, v) in self.links:
            self.links[(u, v)]["status"] = status
        if (v, u) in self.links:
            self.links[(v, u)]["status"] = status

    def shortest_path(self, src: str, dst: str, vlan: int | None = None) -> list[str] | None:
        if src == dst:
            return [src]
        queue: deque[list[str]] = deque([[src]])
        visited: set[str] = {src}
        while queue:
            path = queue.popleft()
            curr = path[-1]
            if curr == dst:
                return path
            for (u, v), link in self.links.items():
                if u != curr or link["status"] != "up":
                    continue
                if vlan is not None and vlan not in link["vlans"]:
                    continue
                if v not in visited:
                    visited.add(v)
                    queue.append([*path, v])
        return None

    def egress_port_for_next_hop(self, current: str, next_hop: str) -> int | None:
        link = self.links.get((current, next_hop))
        return link["local_port"] if link and link["status"] == "up" else None


class FullSDNFabricController(app_manager.OSKenApp):
    """Full-SDN OpenFlow 1.3 Controller with Zero OFPP_NORMAL usage."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        self.policy = PolicyEngine(POLICY_FILE)
        self.datapaths: dict[int, Any] = {}
        self.topo = FabricTopology()

        # Host tracking: IP -> {mac, dpid, port, vlan, last_seen}
        self.hosts_by_ip: dict[str, dict[str, Any]] = {}
        self.hosts_by_mac: dict[str, dict[str, Any]] = {}
        # Per-switch MAC table: dpid -> vlan -> mac -> port
        self.mac_to_port: dict[int, dict[int, dict[str, int]]] = defaultdict(lambda: defaultdict(dict))

        # Port role profiles: dpid -> port_no -> {role, vlan, allowed_vlans}
        self.port_profiles: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)

        # Flow audit and stats
        self.installed_flows: list[dict[str, Any]] = []
        self.file_lock = threading.Lock()
        self.stats = {
            "packet_in_count": 0,
            "proxy_arp_count": 0,
            "policy_drop_count": 0,
            "anti_spoof_drop_count": 0,
            "l2_flow_count": 0,
            "l3_flow_count": 0,
            "failover_count": 0,
        }

        self._init_source_of_truth_inventory()
        self._write_flows()
        self._write_state()
        self._start_admin_socket()
        self.logger.info("Khởi tạo OS-Ken Full-SDN Fabric Controller (Không sử dụng OFPP_NORMAL)")

    def _init_source_of_truth_inventory(self) -> None:
        """Pre-populate host inventory from vars/network_model.yml for anti-spoof & proxy ARP."""
        inventory = build_host_inventory(NETWORK_MODEL)
        for name, host in inventory.items():
            ip = host.get("ip")
            raw_vlan = host.get("vlan")
            vlan_id = int(raw_vlan) if raw_vlan is not None else 0
            if ip and vlan_id:
                record = {
                    "name": name,
                    "ip": ip,
                    "mac": None,  # learned dynamically or populated
                    "switch": host.get("switch"),
                    "dpid": NAME_DPIDS.get(host.get("switch")),
                    "port": None,
                    "vlan": vlan_id,
                    "kind": host.get("kind", "user"),
                    "group": host.get("group"),
                    "last_seen": utc_now(),
                }
                self.hosts_by_ip[ip] = record

    def _write_flows(self) -> None:
        with self.file_lock:
            temp_file = FABRIC_FLOWS_FILE.with_suffix(".tmp")
            data = json.dumps(self.installed_flows[-3000:], ensure_ascii=False, indent=2)
            temp_file.write_text(data, encoding="utf-8")
            temp_file.replace(FABRIC_FLOWS_FILE)
            # Maintain backward compatibility with installed_flows.json
            FLOWS_FILE.write_text(data, encoding="utf-8")

    def _write_state(self) -> None:
        with self.file_lock:
            state = {
                "timestamp": utc_now(),
                "switches": {
                    dpid: {
                        "name": DPID_NAMES.get(dpid, f"dpid-{dpid}"),
                        "role": SWITCH_ROLES.get(DPID_NAMES.get(dpid, ""), "unknown"),
                        "ports": list(self.topo.switch_ports[DPID_NAMES.get(dpid, "")].keys()),
                    }
                    for dpid in self.datapaths
                },
                "learned_hosts": len(self.hosts_by_mac),
                "stats": self.stats,
                "topology_links": [
                    {
                        "source": u,
                        "target": v,
                        "local_port": data["local_port"],
                        "status": data["status"],
                        "vlans": sorted(data["vlans"]),
                    }
                    for (u, v), data in self.topo.links.items()
                ],
            }
            temp = FABRIC_STATE_FILE.with_suffix(".tmp")
            temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(FABRIC_STATE_FILE)

    def _record_event(self, event_type: str, details: dict[str, Any]) -> None:
        payload = {"timestamp": utc_now(), "event_type": event_type, **details}
        with self.file_lock:
            with EVENTS_FILE.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._write_state()

    def _record_flow(
        self,
        datapath,
        table_id: int,
        priority: int,
        match: Any,
        action: str,
        reason: str,
        policy: str = "runtime",
        cookie: int = 0,
        src: str = "*",
        dst: str = "*",
    ) -> None:
        switch_name = DPID_NAMES.get(datapath.id, f"dpid-{datapath.id}")
        entry = {
            "timestamp": utc_now(),
            "switch": switch_name,
            "switch_role": SWITCH_ROLES.get(switch_name, "unknown"),
            "table_id": table_id,
            "priority": priority,
            "match": str(match),
            "action": action,
            "source": src,
            "destination": dst,
            "reason": reason,
            "policy": policy,
            "cookie": f"0x{cookie:x}",
            "enforcement_switch": switch_name,
        }
        self.installed_flows.append(entry)
        self._write_flows()

    def _start_admin_socket(self) -> None:
        if not hasattr(socket, "AF_UNIX"):
            return
        thread = threading.Thread(target=self._admin_socket_loop, name="cch-fabric-admin", daemon=True)
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
            self.logger.error("Admin socket lỗi: %s", exc)
            return

        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    data = conn.recv(65536).decode("utf-8")
                    req = json.loads(data)
                    resp = self._handle_admin_request(req)
                except Exception as err:  # noqa: BLE001
                    resp = {"ok": False, "message": str(err)}
                conn.sendall(json.dumps(resp, ensure_ascii=False).encode("utf-8"))

    def _handle_admin_request(self, req: dict[str, Any]) -> dict[str, Any]:
        if req.get("token") != ADMIN_TOKEN:
            return {"ok": False, "message": "Token không hợp lệ"}
        action = req.get("action")
        if action == "reload_policy":
            return self.reload_policy()
        if action == "get_state":
            return {"ok": True, "stats": self.stats, "hosts": len(self.hosts_by_mac)}
        return {"ok": False, "message": f"Hành động không hỗ trợ: {action}"}

    def reload_policy(self) -> dict[str, Any]:
        self.policy = PolicyEngine(POLICY_FILE)
        self.logger.info("Đã reload policy thành công")
        for dp in self.datapaths.values():
            self._install_proactive_security_flows(dp)
        return {"ok": True, "message": "Fabric policy reloaded"}

    def add_flow(
        self,
        datapath,
        table_id: int,
        priority: int,
        match: Any,
        actions: list[Any],
        reason: str,
        policy: str = "runtime",
        cookie: int = 0,
        idle_timeout: int = 300,
        hard_timeout: int = 0,
        src: str = "*",
        dst: str = "*",
    ) -> None:
        """Install OpenFlow 1.3 flow rule with explicit output actions (NO OFPP_NORMAL)."""
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
                table_id=table_id,
                cookie=cookie,
                priority=priority,
                match=match,
                instructions=instructions,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout,
            )
        )
        action_name = "DROP" if not actions else "OUTPUT"
        self._record_flow(
            datapath,
            table_id,
            priority,
            match,
            action_name,
            reason,
            policy=policy,
            cookie=cookie,
            src=src,
            dst=dst,
        )

    def add_goto_table_flow(
        self,
        datapath,
        table_id: int,
        priority: int,
        match: Any,
        next_table_id: int,
        apply_actions: list[Any] | None = None,
        reason: str = "Pipeline transition",
        cookie: int = 0,
    ) -> None:
        """Install multi-table goto instruction with optional action application."""
        parser = datapath.ofproto_parser
        instructions: list[Any] = []
        if apply_actions:
            instructions.append(
                parser.OFPInstructionActions(
                    datapath.ofproto.OFPIT_APPLY_ACTIONS,
                    apply_actions,
                )
            )
        instructions.append(parser.OFPInstructionGotoTable(next_table_id))

        datapath.send_msg(
            parser.OFPFlowMod(
                datapath=datapath,
                table_id=table_id,
                cookie=cookie,
                priority=priority,
                match=match,
                instructions=instructions,
                idle_timeout=0,
                hard_timeout=0,
            )
        )

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event: Any) -> None:
        datapath = event.msg.datapath
        dpid = datapath.id
        if dpid not in DPID_NAMES:
            self.logger.error("Từ chối switch ngoài target set: dpid=%016x", dpid)
            return

        self.datapaths[dpid] = datapath
        switch_name = DPID_NAMES[dpid]
        self.logger.info("Kết nối OVS: %s (dpid=%016x)", switch_name, dpid)

        # Request port descriptions to build port maps
        parser = datapath.ofproto_parser
        datapath.send_msg(parser.OFPPortDescStatsRequest(datapath, 0))

        # Clear existing flows on all tables
        self._clear_all_tables(datapath)

        # Install base multi-table pipeline defaults
        self._setup_pipeline_defaults(datapath)
        self._install_proactive_security_flows(datapath)

    def _clear_all_tables(self, datapath) -> None:
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        datapath.send_msg(
            parser.OFPFlowMod(
                datapath=datapath,
                table_id=ofproto.OFPTT_ALL,
                command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY,
                match=parser.OFPMatch(),
            )
        )

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_stats_reply_handler(self, event: Any) -> None:
        datapath = event.msg.datapath
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")
        for port in event.msg.body:
            port_no = port.port_no
            port_name = port.name.decode("utf-8") if isinstance(port.name, bytes) else str(port.name)
            if port_no > datapath.ofproto.OFPP_MAX:
                continue
            self.topo.register_port(switch_name, port_no, port_name)
            self._configure_port_profile(dpid, port_no, port_name)

        self._build_topology_links(dpid)
        self._write_state()

    def _configure_port_profile(self, dpid: int, port_no: int, port_name: str) -> None:
        """Infer port role, access VLAN, or trunk allowed VLANs from network model."""
        switch_name = DPID_NAMES.get(dpid, "")

        # Trunk ports
        trunks = {
            "f1-eth99": ("access_floor1", "core_hq", {93, 101, 120, 140}),
            "core-eth01": ("core_hq", "access_floor1", {93, 101, 120, 140}),
            "f2-eth99": ("access_floor2", "core_hq", {103, 104, 110}),
            "core-eth02": ("core_hq", "access_floor2", {103, 104, 110}),
            "inf-eth99": ("infra_access", "core_hq", {100}),
            "core-eth04": ("core_hq", "infra_access", {100}),
            "br-eth99": ("access_branch", "dist_branch", {50, 93}),
            "bd-eth01": ("dist_branch", "access_branch", {50, 93}),
            # Gateway trunk ports
            "core-eth03": ("core_hq", "gateway", {93, 100, 101, 103, 104, 110, 120, 140}),
            "bd-eth02": ("dist_branch", "gateway", {50}),
            # L2VPN ports for VLAN 93
            "core-eth93p": ("core_hq", "ce_hq1", {93}),
            "core-eth93b": ("core_hq", "ce_hq2", {93}),
            "bd-eth93p": ("dist_branch", "ce_branch1", {93}),
            "bd-eth93b": ("dist_branch", "ce_branch2", {93}),
        }

        if port_name in trunks:
            _, peer, vlans = trunks[port_name]
            role = "gateway" if peer == "gateway" else "trunk"
            self.port_profiles[dpid][port_no] = {
                "name": port_name,
                "role": role,
                "allowed_vlans": vlans,
                "peer": peer,
            }
            return

        # Access ports: match endpoint prefix
        access_vlan = None
        if "h101" in port_name:
            access_vlan = 101
        elif "h93" in port_name:
            access_vlan = 93
        elif "h103" in port_name:
            access_vlan = 103
        elif "h104" in port_name:
            access_vlan = 104
        elif "h110" in port_name:
            access_vlan = 110
        elif "guest" in port_name:
            access_vlan = 120
        elif "iotb" in port_name:
            access_vlan = 50
        elif "iot" in port_name or "ups" in port_name:
            access_vlan = 140
        elif "inf-s" in port_name:
            access_vlan = 100

        self.port_profiles[dpid][port_no] = {
            "name": port_name,
            "role": "access" if access_vlan else "unknown",
            "vlan": access_vlan or 0,
            "allowed_vlans": {access_vlan} if access_vlan else set(),
        }

    def _build_topology_links(self, dpid: int) -> None:
        """Establish inter-switch links between discovered trunk ports."""
        trunk_pairs = [
            ("access_floor1", "f1-eth99", "core_hq", "core-eth01", {93, 101, 120, 140}),
            ("access_floor2", "f2-eth99", "core_hq", "core-eth02", {103, 104, 110}),
            ("infra_access", "inf-eth99", "core_hq", "core-eth04", {100}),
            ("access_branch", "br-eth99", "dist_branch", "bd-eth01", {50, 93}),
        ]
        for sw1, p1_name, sw2, p2_name, vlans in trunk_pairs:
            p1 = self.topo.port_name_to_no.get(sw1, {}).get(p1_name)
            p2 = self.topo.port_name_to_no.get(sw2, {}).get(p2_name)
            if p1 and p2:
                self.topo.add_link(sw1, sw2, p1, p2, vlans=vlans)
                self.topo.add_link(sw2, sw1, p2, p1, vlans=vlans)

        # Intersite L2 link (core_hq <-> dist_branch through L2VPN for VLAN 93)
        core_93 = self.topo.port_name_to_no.get("core_hq", {}).get("core-eth93p")
        dist_93 = self.topo.port_name_to_no.get("dist_branch", {}).get("bd-eth93p")
        if core_93 and dist_93:
            self.topo.add_link("core_hq", "dist_branch", core_93, dist_93, vlans={93})
            self.topo.add_link("dist_branch", "core_hq", dist_93, core_93, vlans={93})

    def _setup_pipeline_defaults(self, datapath) -> None:
        """Setup initial table transition rules across tables 0 -> 10 -> 20 -> 30 -> 40."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Table 0 Table-miss: Packet-In to controller for ingress inspection & MAC learning
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(
            datapath,
            table_id=TABLE_INGRESS_FILTER,
            priority=0,
            match=parser.OFPMatch(),
            actions=actions,
            reason="Table 0 Miss: Ingress classification & learning",
            policy="pipeline_default",
            idle_timeout=0,
        )

        # Table 10 Table-miss: Goto Table 20 (Security Policy)
        self.add_goto_table_flow(
            datapath,
            table_id=TABLE_PROTO_VALIDATION,
            priority=0,
            match=parser.OFPMatch(),
            next_table_id=TABLE_SECURITY_POLICY,
            reason="Table 10 Miss: Chuyển tiếp Table 20",
        )

        # Table 20 Table-miss: DROP (Strict Default-Deny)
        self.add_flow(
            datapath,
            table_id=TABLE_SECURITY_POLICY,
            priority=0,
            match=parser.OFPMatch(),
            actions=[],
            reason="Table 20 Default-Deny: Chặn mọi luồng không được cấp phép",
            policy="default_deny",
            idle_timeout=0,
        )

        # Table 30 Table-miss: Packet-In for path calculation & forwarding installation
        self.add_flow(
            datapath,
            table_id=TABLE_FORWARDING,
            priority=0,
            match=parser.OFPMatch(),
            actions=actions,
            reason="Table 30 Miss: Chuyển controller tính path & cài forwarding",
            policy="forwarding_miss",
            idle_timeout=0,
        )

        # Table 40 Table-miss: DROP
        self.add_flow(
            datapath,
            table_id=TABLE_EGRESS_QOS,
            priority=0,
            match=parser.OFPMatch(),
            actions=[],
            reason="Table 40 Miss: Egress drop",
            policy="egress_drop",
            idle_timeout=0,
        )

    def _install_proactive_security_flows(self, datapath) -> None:
        """Pre-install deterministic security drops in Table 20."""
        parser = datapath.ofproto_parser
        switch_name = DPID_NAMES.get(datapath.id, "")

        # 1. Project Isolation: Drop cross-project traffic (101, 93, 103, 104)
        for src_vlan in PROJECT_VLANS:
            for dst_vlan in PROJECT_VLANS:
                if src_vlan == dst_vlan:
                    # Allow intra-project in Table 20 -> Goto Table 30
                    src_net = ipaddress.ip_network(VLAN_SUBNETS[src_vlan])
                    match_intra = parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ipv4_src=(str(src_net.network_address), str(src_net.netmask)),
                        ipv4_dst=(str(src_net.network_address), str(src_net.netmask)),
                    )
                    self.add_goto_table_flow(
                        datapath,
                        table_id=TABLE_SECURITY_POLICY,
                        priority=350,
                        match=match_intra,
                        next_table_id=TABLE_FORWARDING,
                        reason=f"Cho phép nội bộ Dự án VLAN {src_vlan}",
                        cookie=0x1000,
                    )
                    continue

                src_net = ipaddress.ip_network(VLAN_SUBNETS[src_vlan])
                dst_net = ipaddress.ip_network(VLAN_SUBNETS[dst_vlan])
                match_inter = parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(src_net.network_address), str(src_net.netmask)),
                    ipv4_dst=(str(dst_net.network_address), str(dst_net.netmask)),
                )
                self.add_flow(
                    datapath,
                    table_id=TABLE_SECURITY_POLICY,
                    priority=400,
                    match=match_inter,
                    actions=[],
                    reason=f"Chặn cách ly: VLAN {src_vlan} !-> VLAN {dst_vlan}",
                    policy="hq_project_isolation",
                    cookie=POLICY_COOKIES.get("hq_project_isolation", 0x1001),
                    idle_timeout=0,
                )

        # 2. Block Social Media (10.250.20.20)
        match_social = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_dst="10.250.20.20",
        )
        self.add_flow(
            datapath,
            table_id=TABLE_SECURITY_POLICY,
            priority=500,
            match=match_social,
            actions=[],
            reason="Chặn Social Media (hsocial) tại Table 20",
            policy="block_social_media",
            cookie=0x1304,
            idle_timeout=0,
        )

        # 3. Guest (VLAN 120): Allow Internet & Infra, Deny internal RFC1918
        guest_net = ipaddress.ip_network(VLAN_SUBNETS[120])
        match_guest_deny1 = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=(str(guest_net.network_address), str(guest_net.netmask)),
            ipv4_dst=("10.10.0.0", "255.255.0.0"),
        )
        match_guest_deny2 = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=(str(guest_net.network_address), str(guest_net.netmask)),
            ipv4_dst=("10.20.0.0", "255.255.0.0"),
        )
        # First allow DHCP, DNS, NTP to infra services
        for srv_ip in ("10.10.100.10", "10.10.100.11", "10.10.100.16"):
            match_guest_srv = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=(str(guest_net.network_address), str(guest_net.netmask)),
                ipv4_dst=srv_ip,
            )
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=370,
                match=match_guest_srv,
                next_table_id=TABLE_FORWARDING,
                reason="Guest được phép truy cập bootstrap service",
            )
        self.add_flow(
            datapath,
            table_id=TABLE_SECURITY_POLICY,
            priority=360,
            match=match_guest_deny1,
            actions=[],
            reason="Guest bị chặn truy cập mạng nội bộ HQ 10.10.0.0/16",
            policy="guest_isolation",
            idle_timeout=0,
        )
        self.add_flow(
            datapath,
            table_id=TABLE_SECURITY_POLICY,
            priority=360,
            match=match_guest_deny2,
            actions=[],
            reason="Guest bị chặn truy cập mạng nội bộ Branch 10.20.0.0/16",
            policy="guest_isolation",
            idle_timeout=0,
        )

        # 4. IT Support (VLAN 110) controlled access
        it_net = ipaddress.ip_network(VLAN_SUBNETS[110])
        # Allow IT ICMP echo-request to managed users
        for dst_vlan in (93, 101, 103, 104, 140, 50):
            d_net = ipaddress.ip_network(VLAN_SUBNETS[dst_vlan])
            match_it_icmp = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ip_proto=1,
                icmpv4_type=ICMP_ECHO_REQUEST,
                ipv4_src=(str(it_net.network_address), str(it_net.netmask)),
                ipv4_dst=(str(d_net.network_address), str(d_net.netmask)),
            )
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=450,
                match=match_it_icmp,
                next_table_id=TABLE_FORWARDING,
                reason=f"IT Support được chủ động ICMP tới VLAN {dst_vlan}",
                cookie=POLICY_COOKIES.get("it_support", 0x1301),
            )
            # Allow return ICMP reply to IT Support
            match_it_reply = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ip_proto=1,
                icmpv4_type=ICMP_ECHO_REPLY,
                ipv4_src=(str(d_net.network_address), str(d_net.netmask)),
                ipv4_dst=(str(it_net.network_address), str(it_net.netmask)),
            )
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=450,
                match=match_it_reply,
                next_table_id=TABLE_FORWARDING,
                reason=f"Cho phép ICMP reply từ VLAN {dst_vlan} về IT Support",
                cookie=POLICY_COOKIES.get("it_support_return", 0x1302),
            )

        # 5. Voice Priority flow to h90 (10.250.10.10)
        match_voice = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_dst="10.250.10.10",
        )
        self.add_goto_table_flow(
            datapath,
            table_id=TABLE_SECURITY_POLICY,
            priority=425,
            match=match_voice,
            next_table_id=TABLE_EGRESS_QOS,
            reason="Ưu tiên luồng Voice tới Partner PBX h90",
            cookie=POLICY_COOKIES.get("voice", 0x1200),
        )

        self.logger.info("Đã cài đặt security policy proactive tại Table 20 trên %s", switch_name)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event: Any) -> None:
        """Handle Table-miss packets from Table 0 and Table 30 without using OFPP_NORMAL."""
        msg = event.msg
        datapath = msg.datapath
        dpid = datapath.id
        if dpid not in DPID_NAMES:
            return

        self.stats["packet_in_count"] += 1
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if not eth or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        switch_name = DPID_NAMES[dpid]
        vlan_hdr = pkt.get_protocol(vlan.vlan)
        # Determine effective VLAN
        port_prof = self.port_profiles[dpid].get(in_port, {})
        vlan_id = vlan_hdr.vid if vlan_hdr else port_prof.get("vlan", 0)

        # Anti-Spoof Check on access port
        if port_prof.get("role") == "access":
            expected_vlan = port_prof.get("vlan")
            if vlan_hdr and vlan_hdr.vid != expected_vlan:
                self.stats["anti_spoof_drop_count"] += 1
                self.logger.warning(
                    "ANTI-SPOOF ALERT: Host tại %s port %s gửi VLAN %s trái phép (kỳ vọng %s)",
                    switch_name,
                    in_port,
                    vlan_hdr.vid,
                    expected_vlan,
                )
                self._record_event("ANTI_SPOOF_DROP", {
                    "switch": switch_name,
                    "in_port": in_port,
                    "mac": eth.src,
                    "reason": f"Unauthorized VLAN {vlan_hdr.vid} on access port",
                })
                return

        # Learn MAC -> Port mapping (per-VLAN)
        if vlan_id:
            self.mac_to_port[dpid][vlan_id][eth.src] = in_port
            self.hosts_by_mac[eth.src] = {
                "mac": eth.src,
                "dpid": dpid,
                "switch": switch_name,
                "port": in_port,
                "vlan": vlan_id,
                "last_seen": utc_now(),
            }

        # 1. Handle ARP
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            self._handle_arp(datapath, in_port, eth, arp_pkt, vlan_id)
            return

        # 2. Handle IPv4
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt:
            self._handle_ipv4(datapath, in_port, eth, ip_pkt, vlan_id, msg)
            return

    def _handle_arp(self, datapath, in_port: int, eth: Any, arp_pkt: Any, vlan_id: int) -> None:
        """Proxy ARP for virtual gateways and controlled single-VLAN ARP forwarding."""
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")
        target_ip = arp_pkt.dst_ip
        sender_ip = arp_pkt.src_ip
        sender_mac = arp_pkt.src_mac

        # Learn IP-MAC binding
        if sender_ip in self.hosts_by_ip:
            self.hosts_by_ip[sender_ip]["mac"] = sender_mac
            self.hosts_by_ip[sender_ip]["port"] = in_port
            self.hosts_by_ip[sender_ip]["dpid"] = dpid

        # A. Proxy ARP for Virtual Gateways
        if arp_pkt.opcode == arp.ARP_REQUEST and target_ip in ALL_GATEWAY_IPS:
            self.stats["proxy_arp_count"] += 1
            gateway_mac = GATEWAY_MAC_BRANCH if target_ip in GATEWAY_IPS_BRANCH else GATEWAY_MAC_HQ
            self.logger.debug(
                "PROXY ARP REPLY: %s hỏi gateway %s -> trả về %s",
                sender_ip,
                target_ip,
                gateway_mac,
            )
            self._send_arp_reply(datapath, in_port, target_ip, gateway_mac, sender_ip, sender_mac)
            return

        # B. Intra-VLAN ARP
        if arp_pkt.opcode == arp.ARP_REQUEST:
            # Drop cross-VLAN ARP (hosts must use gateway)
            target_host = self.hosts_by_ip.get(target_ip)
            if target_host and target_host.get("vlan") and target_host["vlan"] != vlan_id:
                self.logger.debug("DROP cross-vlan ARP: %s -> %s", sender_ip, target_ip)
                return

            # If target MAC is known, unicast ARP or proxy reply
            if target_host and target_host.get("mac"):
                dst_mac = target_host["mac"]
                target_dpid = target_host.get("dpid")
                target_port = target_host.get("port")
                if target_dpid == dpid and target_port:
                    self._send_packet_out(datapath, target_port, eth, arp_pkt)
                    return

            # Controlled flood strictly within same switch & same VLAN ports
            self._flood_in_vlan(datapath, in_port, vlan_id, eth, arp_pkt)
            return

        if arp_pkt.opcode == arp.ARP_REPLY:
            # Deliver to target
            target_mac = arp_pkt.dst_mac
            out_port = self.mac_to_port[dpid][vlan_id].get(target_mac)
            if out_port and out_port != in_port:
                self._send_packet_out(datapath, out_port, eth, arp_pkt)

    def _send_arp_reply(
        self,
        datapath,
        out_port: int,
        sender_ip: str,
        sender_mac: str,
        target_ip: str,
        target_mac: str,
    ) -> None:
        """Synthesize and output an ARP reply packet directly without OFPP_NORMAL."""
        reply_pkt = packet.Packet()
        reply_pkt.add_protocol(
            ethernet.ethernet(
                ethertype=ether_types.ETH_TYPE_ARP,
                dst=target_mac,
                src=sender_mac,
            )
        )
        reply_pkt.add_protocol(
            arp.arp(
                opcode=arp.ARP_REPLY,
                src_mac=sender_mac,
                src_ip=sender_ip,
                dst_mac=target_mac,
                dst_ip=target_ip,
            )
        )
        reply_pkt.serialize()

        parser = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(out_port)]
        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=datapath.ofproto.OFP_NO_BUFFER,
                in_port=datapath.ofproto.OFPP_CONTROLLER,
                actions=actions,
                data=reply_pkt.data,
            )
        )

    def _flood_in_vlan(self, datapath, in_port: int, vlan_id: int, eth: Any, payload: Any) -> None:
        """Controlled flood: output ONLY to ports member of vlan_id on this switch (NO OFPP_NORMAL)."""
        dpid = datapath.id
        parser = datapath.ofproto_parser
        out_ports: list[int] = []

        for port_no, prof in self.port_profiles[dpid].items():
            if port_no == in_port:
                continue
            if prof.get("role") == "access" and prof.get("vlan") == vlan_id:
                out_ports.append(port_no)
            elif prof.get("role") in {"trunk", "l2vpn"} and vlan_id in prof.get("allowed_vlans", set()):
                out_ports.append(port_no)

        if not out_ports:
            return

        actions = [parser.OFPActionOutput(p) for p in out_ports]
        pkt = packet.Packet()
        pkt.add_protocol(eth)
        pkt.add_protocol(payload)
        pkt.serialize()
        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=datapath.ofproto.OFP_NO_BUFFER,
                in_port=in_port,
                actions=actions,
                data=pkt.data,
            )
        )

    def _send_packet_out(self, datapath, out_port: int, eth: Any, payload: Any) -> None:
        """Send packet out to a single designated physical port."""
        parser = datapath.ofproto_parser
        pkt = packet.Packet()
        pkt.add_protocol(eth)
        pkt.add_protocol(payload)
        pkt.serialize()
        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=datapath.ofproto.OFP_NO_BUFFER,
                in_port=datapath.ofproto.OFPP_CONTROLLER,
                actions=[parser.OFPActionOutput(out_port)],
                data=pkt.data,
            )
        )

    def _handle_ipv4(self, datapath, in_port: int, eth: Any, ip_pkt: Any, vlan_id: int, msg: Any) -> None:
        """Forwarding & Routing Engine without OFPP_NORMAL."""
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")
        parser = datapath.ofproto_parser
        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst

        # Query Security Policy
        decision = self.policy.decide_ip(src_ip, dst_ip)
        if decision["action"] == "deny":
            self.stats["policy_drop_count"] += 1
            self.logger.info("POLICY DROP: %s -> %s tại %s: %s", src_ip, dst_ip, switch_name, decision["reason"])
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
            )
            self.add_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=300,
                match=match,
                actions=[],
                reason=decision["reason"],
                policy="reactive_policy_drop",
                idle_timeout=180,
                src=src_ip,
                dst=dst_ip,
            )
            return

        # Traffic is ALLOWED -> Calculate forwarding / routing
        # Check if traffic is destined for an external / partner service (outside 6 OVS)
        dest_host = self.hosts_by_ip.get(dst_ip)
        is_external = dest_host is None or dest_host.get("kind") == "service"

        if is_external:
            self._route_to_external_gateway(datapath, in_port, eth, ip_pkt, msg)
            return

        # Internal target
        target_vlan = dest_host.get("vlan")
        target_switch = dest_host.get("switch")

        if target_vlan == vlan_id:
            # L2 Intra-VLAN Forwarding
            self._forward_l2_intra_vlan(datapath, in_port, eth, ip_pkt, vlan_id, dest_host, msg)
        else:
            # L3 Inter-VLAN Routing (via virtual gateway rewrite)
            self._route_l3_inter_vlan(datapath, in_port, eth, ip_pkt, vlan_id, dest_host, msg)

    def _forward_l2_intra_vlan(
        self,
        datapath,
        in_port: int,
        eth: Any,
        ip_pkt: Any,
        vlan_id: int,
        dest_host: dict[str, Any],
        msg: Any,
    ) -> None:
        """L2 Intra-VLAN path: Find shortest path across switches, install explicit output flow."""
        dpid = datapath.id
        switch_name = DPID_NAMES[dpid]
        target_switch = dest_host["switch"]
        parser = datapath.ofproto_parser

        path = self.topo.shortest_path(switch_name, target_switch, vlan=vlan_id)
        if not path:
            self.logger.warning("Không tìm thấy đường L2 từ %s tới %s cho VLAN %s", switch_name, target_switch, vlan_id)
            return

        # Determine egress port on current switch
        if len(path) == 1:
            # Destination is directly connected to this switch
            out_port = dest_host.get("port") or self.mac_to_port[dpid][vlan_id].get(eth.dst)
            if not out_port:
                # Find port by matching name
                port_prefix = dest_host["name"]
                for p_no, p_prof in self.port_profiles[dpid].items():
                    if p_prof.get("vlan") == vlan_id and port_prefix in p_prof.get("name", ""):
                        out_port = p_no
                        break
            if not out_port:
                out_port = in_port  # fallback
        else:
            next_switch = path[1]
            out_port = self.topo.egress_port_for_next_hop(switch_name, next_switch)

        if not out_port or out_port == in_port:
            return

        self.stats["l2_flow_count"] += 1
        # Install explicit flow rule at Table 30
        match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=ip_pkt.src,
            ipv4_dst=ip_pkt.dst,
        )
        actions = [parser.OFPActionOutput(out_port)]
        self.add_flow(
            datapath,
            table_id=TABLE_FORWARDING,
            priority=200,
            match=match,
            actions=actions,
            reason=f"L2 Forwarding explicit tới {out_port}",
            policy="l2_forwarding",
            idle_timeout=180,
            src=ip_pkt.src,
            dst=ip_pkt.dst,
        )

        # Output the current packet
        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=msg.data if msg.buffer_id == datapath.ofproto.OFP_NO_BUFFER else None,
            )
        )

    def _route_l3_inter_vlan(
        self,
        datapath,
        in_port: int,
        eth: Any,
        ip_pkt: Any,
        vlan_id: int,
        dest_host: dict[str, Any],
        msg: Any,
    ) -> None:
        """L3 Inter-VLAN Routing: Rewrite source MAC to gateway, dest MAC to host, decrement TTL."""
        dpid = datapath.id
        switch_name = DPID_NAMES[dpid]
        parser = datapath.ofproto_parser
        target_switch = dest_host["switch"]
        target_ip = ip_pkt.dst
        target_mac = dest_host.get("mac") or eth.dst
        gateway_mac = GATEWAY_MAC_BRANCH if switch_name == "dist_branch" else GATEWAY_MAC_HQ

        path = self.topo.shortest_path(switch_name, target_switch)
        if not path:
            return

        if len(path) == 1:
            out_port = dest_host.get("port") or self.mac_to_port[dpid][dest_host["vlan"]].get(target_mac)
            if not out_port:
                for p_no, p_prof in self.port_profiles[dpid].items():
                    if p_prof.get("vlan") == dest_host["vlan"]:
                        out_port = p_no
                        break
        else:
            next_switch = path[1]
            out_port = self.topo.egress_port_for_next_hop(switch_name, next_switch)

        if not out_port:
            return

        self.stats["l3_flow_count"] += 1
        actions = [
            parser.OFPActionSetField(eth_src=gateway_mac),
            parser.OFPActionSetField(eth_dst=target_mac),
            parser.OFPActionDecNwTtl(),
            parser.OFPActionOutput(out_port),
        ]
        match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=ip_pkt.src,
            ipv4_dst=ip_pkt.dst,
        )
        self.add_flow(
            datapath,
            table_id=TABLE_FORWARDING,
            priority=250,
            match=match,
            actions=actions,
            reason=f"L3 Routing: rewrite gateway {gateway_mac}, output {out_port}",
            policy="l3_routing",
            idle_timeout=180,
            src=ip_pkt.src,
            dst=ip_pkt.dst,
        )

        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=msg.data if msg.buffer_id == datapath.ofproto.OFP_NO_BUFFER else None,
            )
        )

    def _route_to_external_gateway(self, datapath, in_port: int, eth: Any, ip_pkt: Any, msg: Any) -> None:
        """Route to external site breakout port (core-eth03 or bd-eth02) to reach firewall/Internet."""
        dpid = datapath.id
        switch_name = DPID_NAMES[dpid]
        parser = datapath.ofproto_parser

        # If on access switch, forward along trunk to core_hq or dist_branch
        gateway_switch = "dist_branch" if switch_name in {"access_branch", "dist_branch"} else "core_hq"
        path = self.topo.shortest_path(switch_name, gateway_switch)
        if not path:
            return

        if len(path) == 1:
            # On gateway switch itself: output to router port
            port_name = "bd-eth02" if switch_name == "dist_branch" else "core-eth03"
            out_port = self.topo.port_name_to_no.get(switch_name, {}).get(port_name)
        else:
            next_switch = path[1]
            out_port = self.topo.egress_port_for_next_hop(switch_name, next_switch)

        if not out_port:
            return

        actions = [
            parser.OFPActionDecNwTtl(),
            parser.OFPActionOutput(out_port),
        ]
        match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_src=ip_pkt.src,
            ipv4_dst=ip_pkt.dst,
        )
        self.add_flow(
            datapath,
            table_id=TABLE_FORWARDING,
            priority=220,
            match=match,
            actions=actions,
            reason=f"External gateway steering tới {out_port}",
            policy="external_breakout",
            idle_timeout=180,
            src=ip_pkt.src,
            dst=ip_pkt.dst,
        )

        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=msg.data if msg.buffer_id == datapath.ofproto.OFP_NO_BUFFER else None,
            )
        )

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, event: Any) -> None:
        """Handle link failure and trigger shortest path failover."""
        msg = event.msg
        datapath = msg.datapath
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")
        port_no = msg.desc.port_no
        state = msg.desc.state
        link_down = (state & datapath.ofproto.OFPPS_LINK_DOWN) != 0

        self.stats["failover_count"] += 1
        peer_info = self.topo.port_to_neighbor.get((switch_name, port_no))
        if peer_info:
            peer_switch, _ = peer_info
            status = "down" if link_down else "up"
            self.topo.set_link_status(switch_name, peer_switch, status)
            self.logger.warning(
                "FAILOVER DETECTED: Link %s <-> %s chuyển sang trạng thái %s",
                switch_name,
                peer_switch,
                status,
            )
            self._record_event("FAILOVER", {
                "switch": switch_name,
                "peer_switch": peer_switch,
                "port_no": port_no,
                "status": status,
            })

            # Flush stale flows associated with this port
            parser = datapath.ofproto_parser
            datapath.send_msg(
                parser.OFPFlowMod(
                    datapath=datapath,
                    table_id=datapath.ofproto.OFPTT_ALL,
                    command=datapath.ofproto.OFPFC_DELETE,
                    out_port=port_no,
                    out_group=datapath.ofproto.OFPG_ANY,
                    match=parser.OFPMatch(),
                )
            )
