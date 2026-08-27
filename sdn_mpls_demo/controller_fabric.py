#!/usr/bin/env python3
"""OS-Ken OpenFlow 1.3 Full-SDN Fabric Controller for CCH Enterprise Network.

Scope:
  Controls the 6-switch enterprise OVS fabric:
    - access_floor1 (dpid 0x0001)
    - access_floor2 (dpid 0x0002)
    - core_hq (dpid 0x0003)
    - access_branch (dpid 0x0004)
    - dist_branch (dpid 0x0005)
    - infra_access (dpid 0x0006)

Boundaries (Outside SDN):
  Firewalls (fw_hq, fw_telesale), CEs, provider MPLS L2VPN transparent bridges,
  and IPsec tunnel abstractions remain outside the SDN domain.

VLAN & Port Boundary:
  OVS port access tagging (tag=) and trunking (trunks=) are handled at the port
  layer. The OpenFlow controller performs multi-table classification, per-VLAN
  learning, anti-spoof validation, and explicit port output without OFPP_NORMAL.

OpenFlow 1.3 Multi-Table Dataplane Pipeline:
  Table 0  (TABLE_INGRESS_FILTER):
    - Classify in_port, validate VLAN tags.
    - Legitimate packets execute GotoTable(10).
    - Spoofed VLAN tags on access ports are DROPPED.
  Table 10 (TABLE_PROTO_VALIDATION):
    - Legitimate ARP sent to Controller for Proxy ARP handling.
    - Anti-spoof IP: Valid source IP/subnet executes GotoTable(20).
    - Spoofed source IPs are DROPPED.
  Table 20 (TABLE_SECURITY_POLICY):
    - Enforce Project Isolation (Drop cross-traffic between VLAN 101, 93, 103, 104).
    - Enforce Guest Boundaries (Allow Internet/Infra, Drop internal RFC1918).
    - Enforce IoT Boundaries (Allow NMS/Infra, Drop users/Internet).
    - Enforce IT Support Least Privilege (Allow ICMP/SSH/RDP to users, Drop unsolicited reverse).
    - Block Social Media (Drop 10.250.20.20).
    - Flow-level Voice Priority (Higher priority flow rule to PBX h90).
    - Allowed flows execute GotoTable(30).
    - Table-miss: Strict Default-Deny (DROP).
  Table 30 (TABLE_FORWARDING):
    - Wire-speed dataplane forwarding for all installed flows.
    - Table-miss: PacketIn to Controller on first packet ONLY.
      Controller computes shortest path and installs explicit forward and reverse
      flows on ALL SWITCHES along the path.

CRITICAL ARCHITECTURAL GUARANTEES:
  1. ZERO usage of OFPP_NORMAL. Every action is explicit OFPActionOutput(port).
  2. Multi-hop flow installation on all switches in path (both forward and reverse).
  3. Real Primary (core-eth93p <-> bd-eth93p) and Backup (core-eth93b <-> bd-eth93b) L2VPN failover.
  4. Honest QoS: Flow-level priority in Table 20 transitioning to Table 30 (no fake queues).
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
    from os_ken.controller.handler import CONFIG_DISPATCHER, DEAD_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from os_ken.lib.packet import (
        arp,
        dhcp,
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
        ETH_TYPE_IPV6 = 0x86DD

    class _MockOfpEvent:
        EventOFPSwitchFeatures = "EventOFPSwitchFeatures"
        EventOFPPortDescStatsReply = "EventOFPPortDescStatsReply"
        EventOFPPacketIn = "EventOFPPacketIn"
        EventOFPPortStatus = "EventOFPPortStatus"
        EventOFPStateChange = "EventOFPStateChange"

    app_manager = _MockAppManager()
    ofp_event = _MockOfpEvent()
    CONFIG_DISPATCHER = "config"
    MAIN_DISPATCHER = "main"
    DEAD_DISPATCHER = "dead"

    def set_ev_cls(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    class _MockARP:
        ARP_REQUEST = 1
        ARP_REPLY = 2

        def arp(self, **kwargs):
            return kwargs

    ofproto_v1_3 = _MockOfprotoV13()
    ether_types = _MockEtherTypes()
    class _MockPacketModule:
        class Packet:
            def __init__(self, data=b"") -> None:
                self.data = data
                self.protocols: list[Any] = []

            def add_protocol(self, proto: Any) -> None:
                self.protocols.append(proto)

            def get_protocol(self, proto_cls: Any) -> Any:
                for p in self.protocols:
                    if isinstance(p, proto_cls) or getattr(p, "_proto_type", None) == proto_cls:
                        return p
                return None

            def serialize(self) -> None:
                pass

    class _MockEthernetModule:
        class ethernet:
            def __init__(self, **kwargs) -> None:
                for k, v in kwargs.items():
                    setattr(self, k, v)

    class _MockVlanModule:
        class vlan:
            def __init__(self, **kwargs) -> None:
                for k, v in kwargs.items():
                    setattr(self, k, v)

    class _MockArpModule:
        ARP_REQUEST = 1
        ARP_REPLY = 2

        class arp:
            def __init__(self, **kwargs) -> None:
                for k, v in kwargs.items():
                    setattr(self, k, v)

    ethernet = _MockEthernetModule()
    vlan = _MockVlanModule()
    arp = _MockArpModule()
    packet = _MockPacketModule()
    class _MockDhcpModule:
        class dhcp:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
    class _MockTcpModule:
        class tcp:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
    class _MockUdpModule:
        class udp:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
    class _MockIcmpModule:
        class icmp:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
    class _MockIpv4Module:
        class ipv4:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
    icmp = _MockIcmpModule()
    ipv4 = _MockIpv4Module()
    tcp = _MockTcpModule()
    udp = _MockUdpModule()
    dhcp = _MockDhcpModule()

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
    from .runtime_contract import RUNTIME_COLLAPSED_GATEWAYS, source_truth_runtime_links
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
    from sdn_mpls_demo.runtime_contract import RUNTIME_COLLAPSED_GATEWAYS, source_truth_runtime_links

BASE_DIR = Path(__file__).resolve().parent
POLICY_FILE = Path(os.environ.get("SDN_POLICY_FILE", BASE_DIR / "policy.yml"))
RUNTIME_DIR = BASE_DIR / "runtime"
FLOWS_FILE = RUNTIME_DIR / "installed_flows.json"
FABRIC_FLOWS_FILE = RUNTIME_DIR / "fabric_flows.json"
FABRIC_STATE_FILE = RUNTIME_DIR / "fabric_state.json"
EVENTS_FILE = RUNTIME_DIR / "events.jsonl"
ADMIN_SOCKET = Path(os.environ.get("CCH_OSKEN_ADMIN_SOCKET", "/tmp/cch_osken_admin.sock"))
ADMIN_TOKEN = os.environ.get("CCH_OSKEN_ADMIN_TOKEN", "cch-local-admin-token")

# OpenFlow Multi-Table IDs (Honest 4-table pipeline)
TABLE_INGRESS_FILTER = 0    # Ingress port/VLAN validation & Anti-spoof
TABLE_PROTO_VALIDATION = 10 # Protocol classification: ARP to controller, IP anti-spoof check
TABLE_SECURITY_POLICY = 20  # Policy Rules (Project isolation, Guest, IoT, IT Support, Voice)
TABLE_FORWARDING = 30       # L2 & L3 Forwarding across entire multi-hop path

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

VLAN_GATEWAYS = {
    93: "10.10.93.1",
    100: "10.10.100.1",
    101: "10.10.101.1",
    103: "10.10.103.1",
    104: "10.10.104.1",
    110: "10.10.110.1",
    120: "10.10.120.1",
    140: "10.10.140.1",
    50: "10.20.50.1",
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


def source_truth_port_profiles(model: dict[str, Any] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """Expand the topology model into every controller-managed ingress port profile."""
    model = model or NETWORK_MODEL
    controller_targets = frozenset(controlled_switches(model))
    inventory = build_host_inventory(model)
    profiles: dict[tuple[str, str], dict[str, Any]] = {}
    hosted_vlans: dict[str, set[int]] = defaultdict(set)
    group_indexes: dict[str, int] = defaultdict(int)

    for host_name, endpoint in inventory.items():
        kind = endpoint.get("kind")
        switch_name = str(endpoint.get("switch") or "")
        if switch_name not in controller_targets:
            continue

        if kind in {"user", "guest", "iot"}:
            group_name = str(endpoint["group"])
            group = model["host_groups"][group_name]
            group_indexes[group_name] += 1
            prefix = str(group.get("interface_prefix", group["prefix"]))
            port_name = f"{prefix}-u{group_indexes[group_name]:02d}"
            subnet = str(group["subnet"])
        elif kind == "infrastructure_service":
            service_names = list(model.get("infrastructure_services", {}))
            port_name = f"inf-s{service_names.index(host_name) + 1:02d}"
            subnet = str(model["infrastructure_services"][host_name]["subnet"])
        else:
            continue

        vlan_id = int(endpoint["vlan"])
        profiles[(switch_name, port_name)] = {
            "name": port_name,
            "role": "access",
            "vlan": vlan_id,
            "subnet": subnet,
            "allowed_vlans": {vlan_id},
            "host": host_name,
            "ip": str(endpoint["ip"]),
        }
        hosted_vlans[switch_name].add(vlan_id)

    gateway_vlans: dict[str, set[int]] = defaultdict(set)
    for group in model.get("host_groups", {}).values():
        gateway_vlans[str(group["gateway_node"])].add(int(group["vlan"]))
    for service in model.get("infrastructure_services", {}).values():
        site = str(service.get("site", "hq"))
        core = model.get("collapsed_core_design", {}).get(site, {}).get("runtime_node")
        if core:
            gateway_vlans[str(core)].add(int(service["vlan"]))

    l2vpn_vlans = {
        int(service["customer_vlan"])
        for service in model.get("l2vpn_services", {}).values()
    }
    gateway_nodes = set(RUNTIME_COLLAPSED_GATEWAYS.values())
    infrastructure = model.get("infrastructure", {})

    for left, right, left_port, right_port, _bw, _delay in source_truth_runtime_links(model):
        for switch_name, peer, port_name in (
            (left, right, left_port),
            (right, left, right_port),
        ):
            if switch_name not in controller_targets:
                continue
            if peer in controller_targets:
                role = "trunk"
                allowed_vlans = hosted_vlans[switch_name] | hosted_vlans[peer]
            elif peer in gateway_nodes:
                role = "gateway"
                allowed_vlans = gateway_vlans[switch_name]
            elif infrastructure.get(peer, {}).get("type") == "ce_bridge":
                role = "l2vpn"
                allowed_vlans = l2vpn_vlans
            else:
                continue
            profiles[(switch_name, port_name)] = {
                "name": port_name,
                "role": role,
                "allowed_vlans": set(allowed_vlans),
                "peer": peer,
            }

    return profiles


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FabricTopology:
    """Graph representation of the 6-switch fabric with real Primary/Backup L2VPN failover."""

    def __init__(self) -> None:
        self.switches: set[str] = set(DPID_NAMES.values())
        # (u, v) -> list of circuit dicts:
        # [{"circuit_id": str, "local_port": int, "remote_port": int, "role": "primary"|"backup"|"standard", "status": "up"|"standby"|"down", "vlans": set[int]}]
        self.links: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self.port_to_neighbor: dict[tuple[str, int], dict[str, Any]] = {}
        self.switch_ports: dict[str, dict[int, str]] = defaultdict(dict)
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
        circuit_id: str = "default",
        role: str = "standard",
        status: str = "up",
        vlans: set[int] | None = None,
    ) -> None:
        circuit = {
            "circuit_id": circuit_id,
            "u": u,
            "v": v,
            "local_port": local_port,
            "remote_port": remote_port,
            "role": role,
            "status": status,
            "vlans": vlans or set(VLAN_SUBNETS.keys()),
        }
        # Avoid duplicate circuits
        existing = [c for c in self.links[(u, v)] if c["circuit_id"] == circuit_id]
        if existing:
            existing[0].update(circuit)
        else:
            self.links[(u, v)].append(circuit)
        self.port_to_neighbor[(u, local_port)] = circuit

    def set_port_link_status(self, switch: str, port_no: int, status: str) -> tuple[str, str] | None:
        """Update circuit status based on port status change."""
        circuit = self.port_to_neighbor.get((switch, port_no))
        if not circuit:
            return None
        circuit["status"] = status
        u, v = circuit["u"], circuit["v"]
        peer_circuits = [c for c in self.links[(v, u)] if c["circuit_id"] == circuit["circuit_id"]]
        if peer_circuits:
            peer_circuits[0]["status"] = status
        return u, v

    def active_circuit(self, u: str, v: str, vlan: int | None = None) -> dict[str, Any] | None:
        circuits = self.links.get((u, v), [])
        # Prefer active primary or standard
        for c in circuits:
            if c["status"] == "up" and (vlan is None or vlan in c["vlans"]):
                if c["role"] in {"primary", "standard"}:
                    return c
        # Fallback to backup if primary is down
        for c in circuits:
            if c["role"] == "backup" and c["status"] in {"up", "standby"} and (vlan is None or vlan in c["vlans"]):
                return c
        return None

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
            for (u, v), _ in self.links.items():
                if u != curr:
                    continue
                circ = self.active_circuit(u, v, vlan=vlan)
                if not circ:
                    continue
                if v not in visited:
                    visited.add(v)
                    queue.append([*path, v])
        return None

    def egress_port_for_next_hop(self, current: str, next_hop: str, vlan: int | None = None) -> int | None:
        circ = self.active_circuit(current, next_hop, vlan=vlan)
        return circ["local_port"] if circ else None


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
        self.expected_port_profiles = source_truth_port_profiles()
        self.complete_port_inventories: set[int] = set()

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
        self.active_sessions: set[tuple[str, str]] = set()
        self.vlan93_active_circuit = "primary"
        self.dhcp_client_records: dict[str, dict[str, Any]] = {}

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
                    "mac": None,
                    "switch": host.get("switch"),
                    "dpid": NAME_DPIDS.get(host.get("switch")),
                    "port": None,
                    "vlan": vlan_id,
                    "kind": host.get("kind", "user"),
                    "group": host.get("group"),
                    "last_seen": utc_now(),
                }
                self.hosts_by_ip[ip] = record

        # Pre-load known host MACs from runtime/host_macs.json if present
        macs_file = RUNTIME_DIR / "host_macs.json"
        if macs_file.exists():
            try:
                mac_data = json.loads(macs_file.read_text(encoding="utf-8"))
                for record in self.hosts_by_ip.values():
                    h_name = record["name"]
                    if h_name in mac_data:
                        record["mac"] = mac_data[h_name]
            except Exception:
                pass

        # Pre-discover Mininet host MACs if in live Mininet lab environment
        try:
            import subprocess
            for record in self.hosts_by_ip.values():
                if record.get("mac"):
                    continue
                h_name = record["name"]
                p = subprocess.run(["pgrep", "-f", f"mininet:{h_name}"], capture_output=True, text=True)
                if p.returncode == 0 and p.stdout.strip():
                    pid = p.stdout.strip().splitlines()[0]
                    devs_out = subprocess.run(["mnexec", "-a", pid, "ls", "/sys/class/net"], capture_output=True, text=True)
                    devs = [d for d in devs_out.stdout.split() if d != "lo"]
                    if devs:
                        mac_out = subprocess.run(["mnexec", "-a", pid, "cat", f"/sys/class/net/{devs[0]}/address"], capture_output=True, text=True)
                        mac = mac_out.stdout.strip()
                        if mac:
                            record["mac"] = mac
        except Exception:
            pass

    def _write_flows(self) -> None:
        with self.file_lock:
            data = json.dumps(self.installed_flows[-3000:], ensure_ascii=False, indent=2)
            try:
                temp_file = FABRIC_FLOWS_FILE.with_suffix(".tmp")
                temp_file.write_text(data, encoding="utf-8")
                temp_file.replace(FABRIC_FLOWS_FILE)
            except Exception:
                try:
                    FABRIC_FLOWS_FILE.write_text(data, encoding="utf-8")
                except Exception:
                    pass
            try:
                FLOWS_FILE.write_text(data, encoding="utf-8")
            except Exception:
                pass

    def _write_state(self) -> None:
        with self.file_lock:
            state = {
                "timestamp": utc_now(),
                "switches": {
                    dpid: {
                        "name": DPID_NAMES.get(dpid, f"dpid-{dpid}"),
                        "role": SWITCH_ROLES.get(DPID_NAMES.get(dpid, ""), "unknown"),
                        "ports": list(self.topo.switch_ports[DPID_NAMES.get(dpid, "")].keys()),
                        "port_inventory_complete": dpid in self.complete_port_inventories,
                    }
                    for dpid in self.datapaths
                },
                "learned_hosts": len(self.hosts_by_mac),
                "stats": self.stats,
                "topology_circuits": [
                    {
                        "circuit_id": c["circuit_id"],
                        "source": c["u"],
                        "target": c["v"],
                        "local_port": c["local_port"],
                        "role": c["role"],
                        "status": c["status"],
                        "vlans": sorted(c["vlans"]),
                    }
                    for circuits in self.topo.links.values()
                    for c in circuits
                ],
            }
            try:
                temp = FABRIC_STATE_FILE.with_suffix(".tmp")
                temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                temp.replace(FABRIC_STATE_FILE)
            except Exception:
                try:
                    FABRIC_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

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
        idle_timeout: int = 0,
        hard_timeout: int = 0,
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
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout,
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
        self.port_profiles[dpid].clear()
        self.topo.switch_ports[switch_name].clear()
        self.topo.port_name_to_no[switch_name].clear()
        self.complete_port_inventories.discard(dpid)
        self.logger.info("Kết nối OVS: %s (dpid=%016x)", switch_name, dpid)

        # Clear existing flows on all tables
        self._clear_all_tables(datapath)

        # Request port descriptions to build port maps and install table 0 & 10 flows
        parser = datapath.ofproto_parser
        datapath.send_msg(parser.OFPPortDescStatsRequest(datapath, 0))

        # Setup Table 0-30 pipeline defaults and Table 20 proactive policies
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

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def state_change_handler(self, ev: Any) -> None:
        datapath = getattr(ev, "datapath", None)
        if not datapath:
            return
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")
        if ev.state == MAIN_DISPATCHER:
            self.logger.info("Switch %s (dpid=%016x) bước vào MAIN_DISPATCHER -> gửi PortDescStatsRequest", switch_name, dpid)
            parser = datapath.ofproto_parser
            datapath.send_msg(parser.OFPPortDescStatsRequest(datapath, 0))

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, [CONFIG_DISPATCHER, MAIN_DISPATCHER])
    def port_desc_stats_reply_handler(self, event: Any) -> None:
        datapath = event.msg.datapath
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")
        self.logger.info("Nhận port desc stats reply từ %s (dpid=%016x) với %d ports", switch_name, dpid, len(event.msg.body))
        for port in event.msg.body:
            port_no = port.port_no
            port_name = port.name.decode("utf-8") if isinstance(port.name, bytes) else str(port.name)
            if port_no > datapath.ofproto.OFPP_MAX:
                continue
            self.topo.register_port(switch_name, port_no, port_name)
            self._configure_port_profile(dpid, port_no, port_name)

        reply_more = getattr(datapath.ofproto, "OFPMPF_REPLY_MORE", 1)
        if getattr(event.msg, "flags", 0) & reply_more:
            return

        expected = {
            port_name
            for profile_switch, port_name in self.expected_port_profiles
            if profile_switch == switch_name
        }
        missing = sorted(expected - set(self.topo.port_name_to_no[switch_name]))
        if missing:
            self.logger.error(
                "Missing source-of-truth ports on %s: %s",
                switch_name,
                ", ".join(missing),
            )

        self._build_topology_links(dpid)
        self._install_port_pipeline_flows(datapath)
        self.complete_port_inventories.add(dpid)
        self._write_state()

    def _configure_port_profile(self, dpid: int, port_no: int, port_name: str) -> None:
        """Assign the exact role/VLAN/subnet generated from source-of-truth."""
        switch_name = DPID_NAMES.get(dpid, "")
        profile = self.expected_port_profiles.get((switch_name, port_name))
        if profile is None:
            self.port_profiles[dpid][port_no] = {
                "name": port_name,
                "role": "unknown",
                "vlan": 0,
                "subnet": None,
                "allowed_vlans": set(),
            }
            return

        self.port_profiles[dpid][port_no] = dict(profile)
        host_name = profile.get("host")
        if host_name:
            for record in self.hosts_by_ip.values():
                if record["name"] == host_name:
                    record["port"] = port_no
                    record["dpid"] = dpid
                    break

    def _build_topology_links(self, dpid: int) -> None:
        """Establish inter-switch links including real Primary and Backup L2VPN paths."""
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
                self.topo.add_link(sw1, sw2, p1, p2, circuit_id=f"{sw1}-{sw2}", role="standard", status="up", vlans=vlans)
                self.topo.add_link(sw2, sw1, p2, p1, circuit_id=f"{sw2}-{sw1}", role="standard", status="up", vlans=vlans)

        # Real Primary L2VPN Circuit (core-eth93p <-> bd-eth93p)
        core_93p = self.topo.port_name_to_no.get("core_hq", {}).get("core-eth93p")
        dist_93p = self.topo.port_name_to_no.get("dist_branch", {}).get("bd-eth93p")
        if core_93p and dist_93p:
            self.topo.add_link("core_hq", "dist_branch", core_93p, dist_93p, circuit_id="l2vpn-primary", role="primary", status="up", vlans={93})
            self.topo.add_link("dist_branch", "core_hq", dist_93p, core_93p, circuit_id="l2vpn-primary", role="primary", status="up", vlans={93})

        # Real Backup L2VPN Circuit (core-eth93b <-> bd-eth93b)
        core_93b = self.topo.port_name_to_no.get("core_hq", {}).get("core-eth93b")
        dist_93b = self.topo.port_name_to_no.get("dist_branch", {}).get("bd-eth93b")
        if core_93b and dist_93b:
            self.topo.add_link("core_hq", "dist_branch", core_93b, dist_93b, circuit_id="l2vpn-backup", role="backup", status="standby", vlans={93})
            self.topo.add_link("dist_branch", "core_hq", dist_93b, core_93b, circuit_id="l2vpn-backup", role="backup", status="standby", vlans={93})

    def _setup_pipeline_defaults(self, datapath) -> None:
        """Setup initial table transition rules across tables 0 -> 10 -> 20 -> 30."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Table 0 Default: Drop unclassified frames
        self.add_flow(
            datapath,
            table_id=TABLE_INGRESS_FILTER,
            priority=0,
            match=parser.OFPMatch(),
            actions=[],
            reason="Table 0 Miss: Drop unclassified ingress frame",
            policy="pipeline_default",
            idle_timeout=0,
        )

        # Table 10 Default: Drop non-ARP / non-IPv4 frames
        self.add_flow(
            datapath,
            table_id=TABLE_PROTO_VALIDATION,
            priority=0,
            match=parser.OFPMatch(),
            actions=[],
            reason="Table 10 Miss: Drop non-IP/non-ARP protocols",
            policy="proto_miss_drop",
            idle_timeout=0,
        )

        # Table 20 Default: Strict Default-Deny
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

        # Flush Table 30 on switch connection to clear any stale dynamic flows
        datapath.send_msg(
            parser.OFPFlowMod(
                datapath=datapath,
                table_id=TABLE_FORWARDING,
                command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY,
                match=parser.OFPMatch(),
            )
        )

        # Table 30 Miss: Send PacketIn to Controller on first packet ONLY
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(
            datapath,
            table_id=TABLE_FORWARDING,
            priority=0,
            match=parser.OFPMatch(),
            actions=actions,
            reason="Table 30 Miss: Gói đầu tiên kích hoạt controller cài đặt multi-hop path",
            policy="forwarding_first_packet",
            idle_timeout=0,
        )

        # Table 30: DHCP packets forwarded to Controller for relay and delivery
        for s_port, d_port in ((68, 67), (67, 68), (67, 67)):
            self.add_flow(
                datapath,
                table_id=TABLE_FORWARDING,
                priority=300,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=17,
                    udp_src=s_port,
                    udp_dst=d_port,
                ),
                actions=actions,
                reason=f"DHCP UDP {s_port}->{d_port} chuyển lên Controller xử lý Relay",
                idle_timeout=0,
            )

    def _install_port_pipeline_flows(self, datapath) -> None:
        """Install Table 0 and Table 10 flows for each discovered port on this datapath."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")

        for port_no, prof in self.port_profiles[dpid].items():
            role = prof.get("role")

            if role == "access":
                vlan_id = prof.get("vlan", 0)
                subnet_str = prof.get("subnet")

                # Table 0: Access Ingress Classification
                # Frame must be untagged (vlan_vid=OFPVID_NONE)
                # Apply Actions: push_vlan(0x8100) + set_field(vlan_vid=vlan_id | OFPVID_PRESENT)
                # Then Goto Table 10 (TABLE_PROTO_VALIDATION)
                match_t0_untagged = parser.OFPMatch(in_port=port_no, vlan_vid=ofproto_v1_3.OFPVID_NONE)
                apply_vlan_tag = [
                    parser.OFPActionPushVlan(0x8100),
                    parser.OFPActionSetField(vlan_vid=vlan_id | ofproto_v1_3.OFPVID_PRESENT),
                ]
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_INGRESS_FILTER,
                    priority=100,
                    match=match_t0_untagged,
                    next_table_id=TABLE_PROTO_VALIDATION,
                    apply_actions=apply_vlan_tag,
                    reason=f"Phân loại ingress cổng access {prof['name']} (gắn VLAN {vlan_id})",
                )

                # Table 0: Access Ingress - Any tagged frame arriving on access port is DROPPED
                match_t0_tagged = parser.OFPMatch(in_port=port_no)
                self.add_flow(
                    datapath,
                    table_id=TABLE_INGRESS_FILTER,
                    priority=90,
                    match=match_t0_tagged,
                    actions=[],
                    reason=f"DROP frame có tag trên cổng access {prof['name']}",
                    policy="access_tag_violation_drop",
                    idle_timeout=0,
                )

                # Table 10: Explicit IPv6 DROP (Lab is IPv4-only)
                match_ipv6 = parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_IPV6)
                self.add_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=500,
                    match=match_ipv6,
                    actions=[],
                    reason="Explicit DROP IPv6 (Lab is IPv4-only)",
                    policy="ipv6_drop",
                    idle_timeout=0,
                )

                # Table 10: DHCP Bootstrap Handling (for DHCP-enabled VLANs: 101, 93, 103, 104, 120 and hdhcp)
                if vlan_id in {101, 93, 103, 104, 120} or prof.get("name") == "inf-eth01":
                    # Client Discover / Request (Bootstrap broadcast)
                    match_dhcp_bcast = parser.OFPMatch(
                        in_port=port_no,
                        eth_type=ether_types.ETH_TYPE_IP,
                        ip_proto=17,
                        udp_src=68,
                        udp_dst=67,
                        ipv4_src="0.0.0.0",
                        ipv4_dst="255.255.255.255",
                    )
                    self.add_goto_table_flow(
                        datapath,
                        table_id=TABLE_PROTO_VALIDATION,
                        priority=180,
                        match=match_dhcp_bcast,
                        next_table_id=TABLE_SECURITY_POLICY,
                        reason=f"DHCP bootstrap frame cho phép qua Table 20 trên {prof['name']}",
                    )
                    # Client General DHCP
                    match_dhcp_client = parser.OFPMatch(
                        in_port=port_no,
                        eth_type=ether_types.ETH_TYPE_IP,
                        ip_proto=17,
                        udp_src=68,
                        udp_dst=67,
                    )
                    self.add_goto_table_flow(
                        datapath,
                        table_id=TABLE_PROTO_VALIDATION,
                        priority=180,
                        match=match_dhcp_client,
                        next_table_id=TABLE_SECURITY_POLICY,
                        reason=f"DHCP client frame cho phép qua Table 20 trên {prof['name']}",
                    )
                    # Server Offer / ACK
                    for s_port, d_port in ((67, 68), (67, 67)):
                        match_dhcp_srv = parser.OFPMatch(
                            in_port=port_no,
                            eth_type=ether_types.ETH_TYPE_IP,
                            ip_proto=17,
                            udp_src=s_port,
                            udp_dst=d_port,
                        )
                        self.add_goto_table_flow(
                            datapath,
                            table_id=TABLE_PROTO_VALIDATION,
                            priority=180,
                            match=match_dhcp_srv,
                            next_table_id=TABLE_SECURITY_POLICY,
                            reason=f"DHCP server frame cho phép qua Table 20 trên {prof['name']}",
                        )

                # Table 10: Legitimate ARP to Controller for Proxy ARP
                match_arp = parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_ARP)
                self.add_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=200,
                    match=match_arp,
                    actions=[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)],
                    reason=f"Chuyển ARP cổng access {prof['name']} lên Controller xử lý Proxy ARP",
                    idle_timeout=0,
                )

                # Table 10: Anti-spoof IP check (Port <-> VLAN <-> Subnet IP binding)
                if subnet_str:
                    net = ipaddress.ip_network(subnet_str)
                    match_valid_ip = parser.OFPMatch(
                        in_port=port_no,
                        eth_type=ether_types.ETH_TYPE_IP,
                        ipv4_src=(str(net.network_address), str(net.netmask)),
                    )
                    self.add_goto_table_flow(
                        datapath,
                        table_id=TABLE_PROTO_VALIDATION,
                        priority=150,
                        match=match_valid_ip,
                        next_table_id=TABLE_SECURITY_POLICY,
                        reason=f"Xác thực IP nguồn hợp lệ thuộc {subnet_str} cho {prof['name']}",
                    )

                # Table 10 Anti-spoof DROP: Any other IP on this access port is spoofed!
                match_spoofed_ip = parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_IP)
                self.add_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=100,
                    match=match_spoofed_ip,
                    actions=[],
                    reason=f"ANTI-SPOOF DROP: IP giả mạo không thuộc subnet được gán cho {prof['name']}",
                    policy="anti_spoof_ip",
                    idle_timeout=0,
                )

            elif role == "l2vpn":
                # L2VPN Attachment circuit for VLAN 93 (core-eth93p, core-eth93b, bd-eth93p, bd-eth93b)
                # Untagged customer frame from CE/L2VPN bridge -> classify into VLAN 93
                apply_vlan93_tag = [
                    parser.OFPActionPushVlan(0x8100),
                    parser.OFPActionSetField(vlan_vid=93 | ofproto_v1_3.OFPVID_PRESENT),
                ]
                match_l2vpn_untagged = parser.OFPMatch(in_port=port_no, vlan_vid=ofproto_v1_3.OFPVID_NONE)
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_INGRESS_FILTER,
                    priority=100,
                    match=match_l2vpn_untagged,
                    next_table_id=TABLE_PROTO_VALIDATION,
                    apply_actions=apply_vlan93_tag,
                    reason=f"Phân loại ingress L2VPN attachment {prof['name']} (gắn VLAN 93)",
                )
                # Also accept frame if already carrying VLAN 93 tag
                match_l2vpn_tagged = parser.OFPMatch(in_port=port_no, vlan_vid=93 | ofproto_v1_3.OFPVID_PRESENT)
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_INGRESS_FILTER,
                    priority=100,
                    match=match_l2vpn_tagged,
                    next_table_id=TABLE_PROTO_VALIDATION,
                    reason=f"Chấp nhận frame VLAN 93 đã có tag trên L2VPN {prof['name']}",
                )
                # Table 0: Drop any other tag on L2VPN port
                self.add_flow(
                    datapath,
                    table_id=TABLE_INGRESS_FILTER,
                    priority=90,
                    match=parser.OFPMatch(in_port=port_no),
                    actions=[],
                    reason=f"DROP frame mang tag không hợp lệ trên L2VPN {prof['name']}",
                    policy="l2vpn_tag_violation_drop",
                    idle_timeout=0,
                )

                # Table 10: IPv6 DROP
                self.add_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=500,
                    match=parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_IPV6),
                    actions=[],
                    reason="Explicit DROP IPv6 (Lab is IPv4-only)",
                    policy="ipv6_drop",
                    idle_timeout=0,
                )
                # Table 10: Trunk/L2VPN ARP to Controller
                self.add_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=200,
                    match=parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_ARP),
                    actions=[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)],
                    reason=f"Chuyển ARP trên link L2VPN {prof['name']} lên Controller",
                    idle_timeout=0,
                )
                # Table 10: L2VPN IPv4 to Table 20
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=120,
                    match=parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_IP),
                    next_table_id=TABLE_SECURITY_POLICY,
                    reason=f"Chuyển IPv4 transit từ L2VPN {prof['name']} tới Table 20",
                )

            elif role in {"trunk", "gateway"}:
                # Table 0: Verify 802.1Q tag in allowed_vlans
                allowed_vlans = prof.get("allowed_vlans", set())
                for vid in allowed_vlans:
                    match_vid = parser.OFPMatch(in_port=port_no, vlan_vid=vid | ofproto_v1_3.OFPVID_PRESENT)
                    self.add_goto_table_flow(
                        datapath,
                        table_id=TABLE_INGRESS_FILTER,
                        priority=100,
                        match=match_vid,
                        next_table_id=TABLE_PROTO_VALIDATION,
                        reason=f"Phân loại ingress cổng {role} {prof['name']} (VLAN {vid})",
                    )
                # Drop untagged frames or frames with unauthorized tags on trunk
                match_trunk_drop = parser.OFPMatch(in_port=port_no)
                self.add_flow(
                    datapath,
                    table_id=TABLE_INGRESS_FILTER,
                    priority=90,
                    match=match_trunk_drop,
                    actions=[],
                    reason=f"DROP frame untagged hoặc sai tag trên cổng {role} {prof['name']}",
                    policy="trunk_tag_violation_drop",
                    idle_timeout=0,
                )

                # Table 10: IPv6 DROP
                self.add_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=500,
                    match=parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_IPV6),
                    actions=[],
                    reason="Explicit DROP IPv6 (Lab is IPv4-only)",
                    policy="ipv6_drop",
                    idle_timeout=0,
                )
                # Table 10: Trunk ARP to Controller
                match_trunk_arp = parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_ARP)
                self.add_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=200,
                    match=match_trunk_arp,
                    actions=[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)],
                    reason=f"Chuyển ARP trên link {role} {prof['name']} lên Controller",
                    idle_timeout=0,
                )
                # Table 10: Trunk IPv4 to Table 20
                match_trunk_ip = parser.OFPMatch(in_port=port_no, eth_type=ether_types.ETH_TYPE_IP)
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_PROTO_VALIDATION,
                    priority=120,
                    match=match_trunk_ip,
                    next_table_id=TABLE_SECURITY_POLICY,
                    reason=f"Chuyển IPv4 transit từ {prof['name']} tới Table 20",
                )

    def _install_proactive_security_flows(self, datapath) -> None:
        """Pre-install deterministic security drops and policy transitions in Table 20 without priority collisions."""
        parser = datapath.ofproto_parser
        switch_name = DPID_NAMES.get(datapath.id, "")

        # 1. Block Social Media (10.250.20.20) - Priority 500
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

        # 2. Block Unsolicited Inbound to IT Support (VLAN 110) - Priority 470
        it_net = ipaddress.ip_network(VLAN_SUBNETS[110])
        for u_vlan in (93, 101, 103, 104, 140, 50):
            u_net = ipaddress.ip_network(VLAN_SUBNETS[u_vlan])
            match_unsolicited_to_it = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=(str(u_net.network_address), str(u_net.netmask)),
                ipv4_dst=(str(it_net.network_address), str(it_net.netmask)),
            )
            self.add_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=470,
                match=match_unsolicited_to_it,
                actions=[],
                reason=f"Chặn người dùng VLAN {u_vlan} chủ động truy cập vào IT Support (VLAN 110)",
                policy="it_inbound_block",
                idle_timeout=0,
            )

        # 3. IT Support -> User Management (ICMP Echo, SSH 22, HTTPS 443, RDP 3389, WinRM 5985/5986) - Priority 460
        for dst_vlan in (93, 101, 103, 104, 140, 50):
            d_net = ipaddress.ip_network(VLAN_SUBNETS[dst_vlan])
            # IT ICMP Echo Request to users
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=460,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=1,
                    icmpv4_type=ICMP_ECHO_REQUEST,
                    ipv4_src=(str(it_net.network_address), str(it_net.netmask)),
                    ipv4_dst=(str(d_net.network_address), str(d_net.netmask)),
                ),
                next_table_id=TABLE_FORWARDING,
                reason=f"IT Support được chủ động ICMP tới VLAN {dst_vlan}",
                cookie=POLICY_COOKIES.get("it_support", 0x1301),
            )
            # IT Management TCP ports
            for tcp_port in self.policy.data["policies"]["it_support_controlled_access"]["management_tcp_ports"]:
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_SECURITY_POLICY,
                    priority=460,
                    match=parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ip_proto=6,
                        tcp_dst=tcp_port,
                        ipv4_src=(str(it_net.network_address), str(it_net.netmask)),
                        ipv4_dst=(str(d_net.network_address), str(d_net.netmask)),
                    ),
                    next_table_id=TABLE_FORWARDING,
                    reason=f"IT Support được phép quản trị TCP/{tcp_port} tới VLAN {dst_vlan}",
                    cookie=POLICY_COOKIES.get("it_support", 0x1301),
                )
        # 4. Scoped Voice Traffic to PBX h90 (10.250.10.10) - Priority 440 (Project 1-4 & IT Support ONLY)
        for voice_vlan in (*PROJECT_VLANS, 110):
            v_net = ipaddress.ip_network(VLAN_SUBNETS[voice_vlan])
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=440,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(v_net.network_address), str(v_net.netmask)),
                    ipv4_dst="10.250.10.10",
                ),
                next_table_id=TABLE_FORWARDING,
                reason=f"Lưu lượng Voice từ VLAN {voice_vlan} tới PBX h90",
                cookie=POLICY_COOKIES.get("voice", 0x1200),
            )

        # 5. Project Isolation: Drop cross-project traffic between VLAN 101, 93, 103, 104 - Priority 420
        for src_vlan in PROJECT_VLANS:
            for dst_vlan in PROJECT_VLANS:
                if src_vlan != dst_vlan:
                    s_net = ipaddress.ip_network(VLAN_SUBNETS[src_vlan])
                    d_net = ipaddress.ip_network(VLAN_SUBNETS[dst_vlan])
                    self.add_flow(
                        datapath,
                        table_id=TABLE_SECURITY_POLICY,
                        priority=420,
                        match=parser.OFPMatch(
                            eth_type=ether_types.ETH_TYPE_IP,
                            ipv4_src=(str(s_net.network_address), str(s_net.netmask)),
                            ipv4_dst=(str(d_net.network_address), str(d_net.netmask)),
                        ),
                        actions=[],
                        reason=f"Chặn cách ly dự án: VLAN {src_vlan} !-> VLAN {dst_vlan}",
                        policy="hq_project_isolation",
                        cookie=POLICY_COOKIES.get("hq_project_isolation", 0x1001),
                        idle_timeout=0,
                    )

        # 6. IoT Services ALLOW (Priority 410) & IoT Isolation DROP (Priority 400)
        for iot_vlan in (140, 50):
            iot_net = ipaddress.ip_network(VLAN_SUBNETS[iot_vlan])
            # IoT to NMS monitoring (10.10.100.14), DNS (10.10.100.11), DHCP (10.10.100.10), NTP (10.10.100.16)
            for srv_ip in ("10.10.100.14", "10.10.100.11", "10.10.100.10", "10.10.100.16"):
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_SECURITY_POLICY,
                    priority=410,
                    match=parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ipv4_src=(str(iot_net.network_address), str(iot_net.netmask)),
                        ipv4_dst=srv_ip,
                    ),
                    next_table_id=TABLE_FORWARDING,
                    reason=f"IoT VLAN {iot_vlan} được phép gửi telemetry tới {srv_ip}",
                )
            # IoT Drop all unauthorized destinations (lateral movement, Internet, user VLANs)
            self.add_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=400,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(iot_net.network_address), str(iot_net.netmask)),
                ),
                actions=[],
                reason=f"IoT VLAN {iot_vlan} bị chặn truy cập mạng người dùng, Internet và dịch vụ khác",
                policy="iot_isolation",
                idle_timeout=0,
            )

        # 7. Guest Bootstrap ALLOW (Priority 390) & RFC1918 Internal DROP (Priority 385)
        guest_net = ipaddress.ip_network(VLAN_SUBNETS[120])
        for srv_ip in ("10.10.100.10", "10.10.100.11", "10.10.100.16"):
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=390,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(guest_net.network_address), str(guest_net.netmask)),
                    ipv4_dst=srv_ip,
                ),
                next_table_id=TABLE_FORWARDING,
                reason=f"Guest được phép truy cập hạ tầng bootstrap {srv_ip}",
            )
        # Guest internal RFC1918 drops
        self.add_flow(
            datapath,
            table_id=TABLE_SECURITY_POLICY,
            priority=385,
            match=parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=(str(guest_net.network_address), str(guest_net.netmask)),
                ipv4_dst=("10.10.0.0", "255.255.0.0"),
            ),
            actions=[],
            reason="Guest bị chặn truy cập mạng nội bộ HQ 10.10.0.0/16",
            policy="guest_isolation",
            idle_timeout=0,
        )
        self.add_flow(
            datapath,
            table_id=TABLE_SECURITY_POLICY,
            priority=385,
            match=parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=(str(guest_net.network_address), str(guest_net.netmask)),
                ipv4_dst=("10.20.0.0", "255.255.0.0"),
            ),
            actions=[],
            reason="Guest bị chặn truy cập mạng nội bộ Branch 10.20.0.0/16",
            policy="guest_isolation",
            idle_timeout=0,
        )

        # 8. Project 1-4 and IT Support -> Infrastructure Services (DHCP, DNS, AD, File, NTP) - Priority 380
        for p_vlan in (*PROJECT_VLANS, 110):
            p_net = ipaddress.ip_network(VLAN_SUBNETS[p_vlan])
            # DHCP (10.10.100.10, UDP 67)
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=380,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=17,
                    udp_dst=67,
                    ipv4_src=(str(p_net.network_address), str(p_net.netmask)),
                    ipv4_dst="10.10.100.10",
                ),
                next_table_id=TABLE_FORWARDING,
                reason="Cho phép DHCP request tới DHCP server 10.10.100.10",
            )
            # DNS (10.10.100.11, UDP 53 & TCP 53)
            for proto, kw in ((17, {"udp_dst": 53}), (6, {"tcp_dst": 53})):
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_SECURITY_POLICY,
                    priority=380,
                    match=parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ip_proto=proto,
                        ipv4_src=(str(p_net.network_address), str(p_net.netmask)),
                        ipv4_dst="10.10.100.11",
                        **kw,
                    ),
                    next_table_id=TABLE_FORWARDING,
                    reason="Cho phép DNS query tới DNS server 10.10.100.11",
                )
            # AD Directory Services (10.10.100.12, TCP 88, 389, 445, 636)
            for ad_port in (88, 389, 445, 636):
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_SECURITY_POLICY,
                    priority=380,
                    match=parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ip_proto=6,
                        tcp_dst=ad_port,
                        ipv4_src=(str(p_net.network_address), str(p_net.netmask)),
                        ipv4_dst="10.10.100.12",
                    ),
                    next_table_id=TABLE_FORWARDING,
                    reason=f"Cho phép AD authentication TCP/{ad_port} tới AD server 10.10.100.12",
                )
            # File Server (10.10.100.13, TCP 445)
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=380,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=6,
                    tcp_dst=445,
                    ipv4_src=(str(p_net.network_address), str(p_net.netmask)),
                    ipv4_dst="10.10.100.13",
                ),
                next_table_id=TABLE_FORWARDING,
                reason="Cho phép File sharing SMB TCP/445 tới File server 10.10.100.13",
            )
            # NTP (10.10.100.16, UDP 123)
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=380,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=17,
                    udp_dst=123,
                    ipv4_src=(str(p_net.network_address), str(p_net.netmask)),
                    ipv4_dst="10.10.100.16",
                ),
                next_table_id=TABLE_FORWARDING,
                reason="Cho phép NTP sync tới NTP server 10.10.100.16",
            )
            # ICMP Echo Ping to Infra Servers for reachability
            for infra_ip in ("10.10.100.10", "10.10.100.11", "10.10.100.12", "10.10.100.13", "10.10.100.14", "10.10.100.15", "10.10.100.16"):
                self.add_goto_table_flow(
                    datapath,
                    table_id=TABLE_SECURITY_POLICY,
                    priority=380,
                    match=parser.OFPMatch(
                        eth_type=ether_types.ETH_TYPE_IP,
                        ip_proto=1,
                        icmpv4_type=ICMP_ECHO_REQUEST,
                        ipv4_src=(str(p_net.network_address), str(p_net.netmask)),
                        ipv4_dst=infra_ip,
                    ),
                    next_table_id=TABLE_FORWARDING,
                    reason=f"Cho phép ping kiểm tra kết nối tới máy chủ hạ tầng {infra_ip}",
                )

        # 9. Scoped Outbound: Projects & IT -> Partner CRM (10.250.10.20), Guest -> Internet (10.250.20.30) - Priority 360
        for p_vlan in (*PROJECT_VLANS, 110):
            p_net = ipaddress.ip_network(VLAN_SUBNETS[p_vlan])
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=360,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(p_net.network_address), str(p_net.netmask)),
                    ipv4_dst="10.250.10.20",
                ),
                next_table_id=TABLE_FORWARDING,
                reason="Cho phép truy cập Partner CRM 10.250.10.20",
            )
            # Outbound Internet for Project & IT
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=360,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(p_net.network_address), str(p_net.netmask)),
                    ipv4_dst="10.250.20.30",
                ),
                next_table_id=TABLE_FORWARDING,
                reason=f"Cho phép truy cập Internet 10.250.20.30 từ VLAN {p_vlan}",
            )
        # Guest to Internet (10.250.20.30)
        self.add_goto_table_flow(
            datapath,
            table_id=TABLE_SECURITY_POLICY,
            priority=360,
            match=parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=(str(guest_net.network_address), str(guest_net.netmask)),
                ipv4_dst="10.250.20.30",
            ),
            next_table_id=TABLE_FORWARDING,
            reason="Guest được phép truy cập Internet 10.250.20.30",
        )

        # 9b. DHCP Bootstrap Policy in Table 20 (Priority 490)
        for s_port, d_port in ((68, 67), (67, 68), (67, 67)):
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=490,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=17,
                    udp_src=s_port,
                    udp_dst=d_port,
                ),
                next_table_id=TABLE_FORWARDING,
                reason=f"DHCP bootstrap UDP {s_port}->{d_port} chuyển tiếp tới Table 30",
            )

        # 10. Intra-Project / Intra-VLAN Allowed Traffic - Priority 350
        for vlan_id in (*PROJECT_VLANS, 110, 120, 140, 50, 100):
            s_net = ipaddress.ip_network(VLAN_SUBNETS[vlan_id])
            self.add_goto_table_flow(
                datapath,
                table_id=TABLE_SECURITY_POLICY,
                priority=350,
                match=parser.OFPMatch(
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=(str(s_net.network_address), str(s_net.netmask)),
                    ipv4_dst=(str(s_net.network_address), str(s_net.netmask)),
                ),
                next_table_id=TABLE_FORWARDING,
                reason=f"Cho phép lưu lượng nội bộ VLAN {vlan_id}",
                cookie=0x1000,
            )

        self.logger.info("Đã cài đặt security policy proactive tại Table 20 trên %s", switch_name)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event: Any) -> None:
        """Handle Table-miss packets from Table 10 and Table 30 without using OFPP_NORMAL."""
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
        port_prof = self.port_profiles[dpid].get(in_port, {})
        allowed_vlans = port_prof.get("allowed_vlans", set())
        vlan_id = (
            vlan_hdr.vid
            if vlan_hdr
            else port_prof.get("vlan") or (next(iter(allowed_vlans)) if len(allowed_vlans) == 1 else 0)
        )

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
            self.logger.debug("PROXY ARP REPLY: %s hỏi gateway %s -> trả về %s", sender_ip, target_ip, gateway_mac)
            self._send_arp_reply(datapath, in_port, target_ip, gateway_mac, sender_ip, sender_mac, vlan_id=vlan_id)
            return

        # B. Intra-VLAN ARP
        if arp_pkt.opcode == arp.ARP_REQUEST:
            # Drop cross-VLAN ARP
            target_host = self.hosts_by_ip.get(target_ip)
            if target_host and target_host.get("vlan") and target_host["vlan"] != vlan_id:
                self.logger.debug("DROP cross-vlan ARP: %s -> %s", sender_ip, target_ip)
                return

            if target_host and target_host.get("mac"):
                dst_mac = target_host["mac"]
                target_dpid = target_host.get("dpid")
                target_port = target_host.get("port")
                if target_dpid == dpid and target_port:
                    self._send_packet_out(datapath, target_port, eth, arp_pkt)
                self._send_arp_reply(datapath, in_port, target_ip, dst_mac, sender_ip, sender_mac, vlan_id=vlan_id)
                return

            self._flood_in_vlan(datapath, in_port, vlan_id, eth, arp_pkt)
            return

        if arp_pkt.opcode == arp.ARP_REPLY:
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
        vlan_id: int = 0,
    ) -> None:
        """Synthesize and output an ARP reply packet directly without OFPP_NORMAL."""
        dpid = datapath.id
        port_prof = self.port_profiles[dpid].get(out_port, {})
        is_tagged = port_prof.get("role") in {"trunk", "gateway", "l2vpn"} and vlan_id > 0

        reply_pkt = packet.Packet()
        if is_tagged:
            reply_pkt.add_protocol(
                ethernet.ethernet(
                    ethertype=ether_types.ETH_TYPE_8021Q,
                    dst=target_mac,
                    src=sender_mac,
                )
            )
            reply_pkt.add_protocol(
                vlan.vlan(
                    vid=vlan_id,
                    ethertype=ether_types.ETH_TYPE_ARP,
                )
            )
        else:
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
            elif prof.get("role") in {"trunk", "gateway"} and vlan_id in prof.get("allowed_vlans", set()):
                out_ports.append(port_no)
            elif prof.get("role") == "l2vpn" and vlan_id == 93:
                port_name = prof.get("name", "")
                if "93p" in port_name and self.vlan93_active_circuit == "primary":
                    out_ports.append(port_no)
                elif "93b" in port_name and self.vlan93_active_circuit == "backup":
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

    def _handle_gateway_icmp(self, datapath, in_port: int, eth: Any, ip_pkt: Any, vlan_id: int, msg: Any) -> None:
        """Respond to ICMP Echo Requests targeting the Virtual Gateway directly from SDN controller."""
        pkt = packet.Packet(msg.data)
        icmp_pkt = pkt.get_protocol(icmp.icmp)
        if not icmp_pkt or icmp_pkt.type != icmp.ICMP_ECHO_REQUEST:
            return

        parser = datapath.ofproto_parser
        gateway_mac = GATEWAY_MAC_BRANCH if ip_pkt.dst in GATEWAY_IPS_BRANCH else GATEWAY_MAC_HQ

        reply_pkt = packet.Packet()
        reply_pkt.add_protocol(
            ethernet.ethernet(
                ethertype=ether_types.ETH_TYPE_IP,
                dst=eth.src,
                src=gateway_mac,
            )
        )
        reply_pkt.add_protocol(
            ipv4.ipv4(
                dst=ip_pkt.src,
                src=ip_pkt.dst,
                proto=ipv4.inet.IPPROTO_ICMP,
                ttl=64,
            )
        )
        reply_pkt.add_protocol(
            icmp.icmp(
                type_=icmp.ICMP_ECHO_REPLY,
                code=0,
                csum=0,
                data=icmp_pkt.data,
            )
        )
        reply_pkt.serialize()
        datapath.send_msg(
            parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=datapath.ofproto.OFP_NO_BUFFER,
                in_port=datapath.ofproto.OFPP_CONTROLLER,
                actions=[parser.OFPActionOutput(in_port)],
                data=reply_pkt.data,
            )
        )

    def _handle_ipv4(self, datapath, in_port: int, eth: Any, ip_pkt: Any, vlan_id: int, msg: Any) -> None:
        """Forwarding & Multi-hop Path Installation on Table 30 without OFPP_NORMAL."""
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")
        parser = datapath.ofproto_parser
        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst
        self.logger.info("HANDLE_IPV4: %s -> %s at %s in_port=%d vlan=%s", src_ip, dst_ip, switch_name, in_port, vlan_id)

        # DHCP Relay packet handling
        if ip_pkt.proto == 17 and hasattr(msg, "data") and msg.data:
            try:
                pkt = packet.Packet(msg.data)
                udp_pkt = pkt.get_protocol(udp.udp)
                if udp_pkt and (udp_pkt.dst_port in {67, 68} or udp_pkt.src_port in {67, 68}):
                    self._handle_dhcp(datapath, in_port, eth, ip_pkt, vlan_id, msg, udp_pkt)
                    return
            except Exception as e:
                self.logger.error("Lỗi khi xử lý DHCP packet: %s", e)

        # Virtual Gateway ICMP Echo Request handling
        if dst_ip in ALL_GATEWAY_IPS:
            self._handle_gateway_icmp(datapath, in_port, eth, ip_pkt, vlan_id, msg)
            return

        # Policy validation with stateful connection tracking
        is_established_return = (src_ip, dst_ip) in self.active_sessions
        if is_established_return:
            decision = {"action": "allow", "reason": "Stateful firewall cho phép lưu lượng phản hồi"}
        else:
            decision = self.policy.decide_ip(src_ip, dst_ip)
            if decision["action"] == "allow":
                self.active_sessions.add((dst_ip, src_ip))
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

        dest_host = self.hosts_by_ip.get(dst_ip)
        src_host = self.hosts_by_ip.get(src_ip)
        is_external = dest_host is None or dest_host.get("kind") == "service"

        if is_external:
            self._route_multi_hop_external(datapath, in_port, eth, ip_pkt, vlan_id, src_host, msg)
        else:
            self._route_multi_hop_internal(datapath, in_port, eth, ip_pkt, vlan_id, src_host, dest_host, msg)

    def _handle_dhcp(self, datapath, in_port: int, eth: Any, ip_pkt: Any, vlan_id: int, msg: Any, udp_pkt: Any) -> None:
        """DHCP Relay Agent: Relays DHCP Discover/Request to hdhcp (10.10.100.10) and delivers Offer/ACK to client."""
        pkt = packet.Packet(msg.data)
        dhcp_pkt = pkt.get_protocol(dhcp.dhcp)
        if not dhcp_pkt:
            return

        dpid = datapath.id
        sw_name = DPID_NAMES.get(dpid, "")

        # 1. CLIENT TO SERVER (Discover / Request)
        if udp_pkt.dst_port == 67 and dhcp_pkt.op == 1:
            chaddr = dhcp_pkt.chaddr
            prof = self.port_profiles[dpid].get(in_port, {})
            client_vlan = prof.get("vlan", 0) or vlan_id
            gateway_ip = VLAN_GATEWAYS.get(client_vlan, f"10.10.{client_vlan}.1")

            self.dhcp_client_records[chaddr] = {
                "dpid": dpid,
                "port": in_port,
                "vlan": client_vlan,
                "gateway_ip": gateway_ip,
            }
            self.logger.info("DHCP RELAY: Client %s on %s port %d VLAN %d (giaddr=%s)", chaddr, sw_name, in_port, client_vlan, gateway_ip)

            # Set giaddr and hops as per RFC 2131
            dhcp_pkt.giaddr = gateway_ip
            dhcp_pkt.hops += 1

            hdhcp_mac = "00:00:00:00:00:6f"
            gateway_mac = GATEWAY_MAC_HQ

            relayed_pkt = packet.Packet()
            relayed_pkt.add_protocol(
                ethernet.ethernet(
                    ethertype=ether_types.ETH_TYPE_IP,
                    dst=hdhcp_mac,
                    src=gateway_mac,
                )
            )
            relayed_pkt.add_protocol(
                ipv4.ipv4(
                    src=gateway_ip,
                    dst="10.10.100.10",
                    proto=17,
                    ttl=64,
                )
            )
            relayed_pkt.add_protocol(
                udp.udp(
                    src_port=67,
                    dst_port=67,
                )
            )
            relayed_pkt.add_protocol(dhcp_pkt)
            relayed_pkt.serialize()

            infra_dpid = NAME_DPIDS.get("infra_access")
            if infra_dpid and infra_dpid in self.datapaths:
                infra_dp = self.datapaths[infra_dpid]
                hdhcp_port = self.topo.port_name_to_no.get("infra_access", {}).get("inf-eth01", 1)
                infra_parser = infra_dp.ofproto_parser
                infra_dp.send_msg(
                    infra_parser.OFPPacketOut(
                        datapath=infra_dp,
                        buffer_id=infra_dp.ofproto.OFP_NO_BUFFER,
                        in_port=infra_dp.ofproto.OFPP_CONTROLLER,
                        actions=[infra_parser.OFPActionOutput(hdhcp_port)],
                        data=relayed_pkt.data,
                    )
                )
            return

        # 2. SERVER TO CLIENT (Offer / ACK)
        if dhcp_pkt.op == 2:
            chaddr = dhcp_pkt.chaddr
            rec = self.dhcp_client_records.get(chaddr)
            if not rec:
                self.logger.warning("DHCP RELAY: Received reply for unknown client %s", chaddr)
                return

            client_dpid = rec["dpid"]
            client_port = rec["port"]
            client_vlan = rec["vlan"]
            gateway_ip = rec["gateway_ip"]
            client_dp = self.datapaths.get(client_dpid)
            if not client_dp:
                return

            self.logger.info("DHCP RELAY: Delivering Offer/ACK to client %s on dpid %d port %d", chaddr, client_dpid, client_port)

            gateway_mac = GATEWAY_MAC_HQ
            client_reply_pkt = packet.Packet()
            client_reply_pkt.add_protocol(
                ethernet.ethernet(
                    ethertype=ether_types.ETH_TYPE_IP,
                    dst=chaddr,
                    src=gateway_mac,
                )
            )
            client_reply_pkt.add_protocol(
                ipv4.ipv4(
                    src=gateway_ip,
                    dst=dhcp_pkt.yiaddr if dhcp_pkt.yiaddr != "0.0.0.0" else "255.255.255.255",
                    proto=17,
                    ttl=64,
                )
            )
            client_reply_pkt.add_protocol(
                udp.udp(
                    src_port=67,
                    dst_port=68,
                )
            )
            client_reply_pkt.add_protocol(dhcp_pkt)
            client_reply_pkt.serialize()

            client_parser = client_dp.ofproto_parser
            client_dp.send_msg(
                client_parser.OFPPacketOut(
                    datapath=client_dp,
                    buffer_id=client_dp.ofproto.OFP_NO_BUFFER,
                    in_port=client_dp.ofproto.OFPP_CONTROLLER,
                    actions=[client_parser.OFPActionOutput(client_port)],
                    data=client_reply_pkt.data,
                )
            )
            return

    def _extract_l4_details(self, msg: Any, ip_pkt: Any) -> tuple[int, int | None, int | None, int | None]:
        """Extract protocol, sport, dport, icmp_type from packet."""
        proto = getattr(ip_pkt, "proto", 6)
        sport: int | None = None
        dport: int | None = None
        icmp_type: int | None = None
        if hasattr(msg, "data") and msg.data:
            try:
                pkt = packet.Packet(msg.data)
                t_pkt = pkt.get_protocol(tcp.tcp)
                u_pkt = pkt.get_protocol(udp.udp)
                i_pkt = pkt.get_protocol(icmp.icmp)
                if t_pkt:
                    proto = 6
                    sport = t_pkt.src_port
                    dport = t_pkt.dst_port
                elif u_pkt:
                    proto = 17
                    sport = u_pkt.src_port
                    dport = u_pkt.dst_port
                elif i_pkt:
                    proto = 1
                    icmp_type = i_pkt.type
            except Exception:
                pass
        return proto, sport, dport, icmp_type

    def _install_dynamic_return_policy(
        self,
        src_ip: str,
        dst_ip: str,
        proto: int,
        sport: int | None,
        dport: int | None,
        icmp_type: int | None,
        paths: list[str],
    ) -> None:
        """Install dynamic 5-tuple return flow in Table 20 with idle timeout.

        Permits ONLY returning packets of this specific established session.
        Prevents servers or users from opening unauthorized unsolicited sessions.
        """
        match_kwargs: dict[str, Any] = {
            "eth_type": ether_types.ETH_TYPE_IP,
            "ip_proto": proto,
            "ipv4_src": dst_ip,
            "ipv4_dst": src_ip,
        }
        timeout = 180
        if proto == 6:
            if dport is not None:
                match_kwargs["tcp_src"] = dport
            if sport is not None:
                match_kwargs["tcp_dst"] = sport
        elif proto == 17:
            if dport is not None:
                match_kwargs["udp_src"] = dport
            if sport is not None:
                match_kwargs["udp_dst"] = sport
        elif proto == 1:
            match_kwargs["icmpv4_type"] = 0  # ICMP Echo Reply only
            timeout = 180

        for sw_name in paths:
            sw_dpid = NAME_DPIDS.get(sw_name)
            if not sw_dpid or sw_dpid not in self.datapaths:
                continue
            sw_dp = self.datapaths[sw_dpid]
            sw_parser = sw_dp.ofproto_parser
            match_dyn_return = sw_parser.OFPMatch(**match_kwargs)
            self.add_goto_table_flow(
                sw_dp,
                table_id=TABLE_SECURITY_POLICY,
                priority=480,
                match=match_dyn_return,
                next_table_id=TABLE_FORWARDING,
                reason=f"Phản hồi session động 5-tuple: {dst_ip} -> {src_ip} proto={proto}",
                idle_timeout=timeout,
            )

    def _route_multi_hop_internal(
        self,
        datapath,
        in_port: int,
        eth: Any,
        ip_pkt: Any,
        src_vlan: int,
        src_host: dict[str, Any] | None,
        dst_host: dict[str, Any],
        msg: Any,
    ) -> None:
        """Install forward and reverse flow rules across ALL switches on the path."""
        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst
        src_switch = (src_host.get("switch") if src_host else None) or DPID_NAMES[datapath.id]
        dst_switch = dst_host["switch"]
        dst_vlan = dst_host["vlan"]
        is_inter_vlan = src_vlan != dst_vlan

        # Determine path
        if not is_inter_vlan:
            path = self.topo.shortest_path(src_switch, dst_switch, vlan=src_vlan)
        else:
            # Route via Core/Gateway switch
            gateway_switch = "dist_branch" if src_switch in {"access_branch", "dist_branch"} and dst_switch in {"access_branch", "dist_branch"} else "core_hq"
            p1 = self.topo.shortest_path(src_switch, gateway_switch, vlan=src_vlan)
            p2 = self.topo.shortest_path(gateway_switch, dst_switch, vlan=dst_vlan)
            if p1 and p2:
                path = p1[:-1] + p2
            else:
                path = None

        if not path:
            self.logger.warning("Không tìm thấy đường đi giữa %s và %s", src_switch, dst_switch)
            return

        target_mac = dst_host.get("mac") or eth.dst
        source_mac = eth.src
        gateway_mac = GATEWAY_MAC_BRANCH if "dist_branch" in path else GATEWAY_MAC_HQ
        gateway_sw_name = "dist_branch" if ("dist_branch" in path and ("access_branch" in path or "dist_branch" in path)) else "core_hq"
        gateway_idx = path.index(gateway_sw_name) if gateway_sw_name in path else 0

        # 1. Install Forward Flows on ALL switches in path
        for i, sw_name in enumerate(path):
            sw_dpid = NAME_DPIDS.get(sw_name)
            if not sw_dpid or sw_dpid not in self.datapaths:
                continue
            sw_dp = self.datapaths[sw_dpid]
            sw_parser = sw_dp.ofproto_parser

            is_last_hop = (i == len(path) - 1)
            if is_last_hop:
                # Last switch: output to target access port
                out_port = dst_host.get("port") or self._find_host_port(sw_dpid, dst_host["name"], dst_vlan)
            else:
                next_sw = path[i + 1]
                egress_vlan = dst_vlan if (is_inter_vlan and i >= gateway_idx) else src_vlan
                out_port = self.topo.egress_port_for_next_hop(sw_name, next_sw, vlan=egress_vlan)

            if not out_port:
                continue

            actions: list[Any] = []
            curr_match_vlan = dst_vlan if (is_inter_vlan and i > gateway_idx) else src_vlan

            if is_inter_vlan and sw_name in {"core_hq", "dist_branch"}:
                # L3 Gateway rewrite & swap VLAN tag to destination VLAN
                actions.extend([
                    sw_parser.OFPActionSetField(vlan_vid=dst_vlan | ofproto_v1_3.OFPVID_PRESENT),
                    sw_parser.OFPActionSetField(eth_src=gateway_mac),
                    sw_parser.OFPActionSetField(eth_dst=target_mac),
                    sw_parser.OFPActionDecNwTtl(),
                ])

            # Strip VLAN tag on final delivery to host or L2VPN bridge
            port_prof = self.port_profiles[sw_dpid].get(out_port, {})
            if is_last_hop and port_prof.get("role") in {"access", "l2vpn"}:
                actions.append(sw_parser.OFPActionPopVlan())

            actions.append(sw_parser.OFPActionOutput(out_port))

            match_fwd = sw_parser.OFPMatch(
                vlan_vid=curr_match_vlan | ofproto_v1_3.OFPVID_PRESENT,
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
            )
            self.add_flow(
                sw_dp,
                table_id=TABLE_FORWARDING,
                priority=250 if is_inter_vlan else 200,
                match=match_fwd,
                actions=actions,
                reason=f"Multi-hop Forward tới {sw_name} port {out_port}",
                policy="l3_routing" if is_inter_vlan else "l2_forwarding",
                idle_timeout=180,
                src=src_ip,
                dst=dst_ip,
            )

        # 2. Install Reverse Flows on ALL switches in path
        rev_path = list(reversed(path))
        rev_gateway_idx = rev_path.index(gateway_sw_name) if gateway_sw_name in rev_path else 0
        for i, sw_name in enumerate(rev_path):
            sw_dpid = NAME_DPIDS.get(sw_name)
            if not sw_dpid or sw_dpid not in self.datapaths:
                continue
            sw_dp = self.datapaths[sw_dpid]
            sw_parser = sw_dp.ofproto_parser

            is_last_rev_hop = (i == len(rev_path) - 1)
            if is_last_rev_hop:
                # Source switch: output to source access port
                rev_out_port = self._find_host_port(sw_dpid, src_host["name"], src_vlan) if src_host else None
                if not rev_out_port and src_host:
                    rev_out_port = src_host.get("port")
                if not rev_out_port and sw_name == DPID_NAMES.get(datapath.id):
                    rev_out_port = in_port
            else:
                next_sw = rev_path[i + 1]
                rev_egress_vlan = src_vlan if (is_inter_vlan and i >= rev_gateway_idx) else dst_vlan
                rev_out_port = self.topo.egress_port_for_next_hop(sw_name, next_sw, vlan=rev_egress_vlan)

            if not rev_out_port:
                continue

            rev_actions: list[Any] = []
            curr_rev_match_vlan = src_vlan if (is_inter_vlan and i > rev_gateway_idx) else dst_vlan

            if is_inter_vlan and sw_name in {"core_hq", "dist_branch"}:
                rev_actions.extend([
                    sw_parser.OFPActionSetField(vlan_vid=src_vlan | ofproto_v1_3.OFPVID_PRESENT),
                    sw_parser.OFPActionSetField(eth_src=gateway_mac),
                    sw_parser.OFPActionSetField(eth_dst=source_mac),
                    sw_parser.OFPActionDecNwTtl(),
                ])

            # Strip VLAN tag on final delivery to source host or L2VPN bridge
            rev_port_prof = self.port_profiles[sw_dpid].get(rev_out_port, {})
            if is_last_rev_hop and rev_port_prof.get("role") in {"access", "l2vpn"}:
                rev_actions.append(sw_parser.OFPActionPopVlan())

            rev_actions.append(sw_parser.OFPActionOutput(rev_out_port))

            match_rev = sw_parser.OFPMatch(
                vlan_vid=curr_rev_match_vlan | ofproto_v1_3.OFPVID_PRESENT,
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=dst_ip,
                ipv4_dst=src_ip,
            )
            self.add_flow(
                sw_dp,
                table_id=TABLE_FORWARDING,
                priority=250 if is_inter_vlan else 200,
                match=match_rev,
                actions=rev_actions,
                reason=f"Multi-hop Reverse tới {sw_name} port {rev_out_port}",
                policy="l3_routing" if is_inter_vlan else "l2_forwarding",
                idle_timeout=180,
                src=dst_ip,
                dst=src_ip,
            )

        # Install dynamic 5-tuple return policy on Table 20
        proto, sport, dport, icmp_type = self._extract_l4_details(msg, ip_pkt)
        self._install_dynamic_return_policy(
            src_ip=src_ip,
            dst_ip=dst_ip,
            proto=proto,
            sport=sport,
            dport=dport,
            icmp_type=icmp_type,
            paths=path,
        )

        self.stats["l3_flow_count" if is_inter_vlan else "l2_flow_count"] += len(path)
        # Send initial packet out of ingress switch
        ingress_out_port = (
            dst_host.get("port")
            if len(path) == 1
            else self.topo.egress_port_for_next_hop(src_switch, path[1], vlan=src_vlan)
        )
        if ingress_out_port:
            parser = datapath.ofproto_parser
            pkt_actions: list[Any] = []
            if is_inter_vlan and src_switch in {"core_hq", "dist_branch"}:
                pkt_actions.extend([
                    parser.OFPActionSetField(eth_src=gateway_mac),
                    parser.OFPActionSetField(eth_dst=target_mac),
                    parser.OFPActionDecNwTtl(),
                ])
            pkt_actions.append(parser.OFPActionOutput(ingress_out_port))
            datapath.send_msg(
                parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=msg.buffer_id,
                    in_port=in_port,
                    actions=pkt_actions,
                    data=msg.data if msg.buffer_id == datapath.ofproto.OFP_NO_BUFFER else None,
                )
            )

    def _route_multi_hop_external(
        self,
        datapath,
        in_port: int,
        eth: Any,
        ip_pkt: Any,
        vlan_id: int,
        src_host: dict[str, Any] | None,
        msg: Any,
    ) -> None:
        """Route to external site breakout port (core-eth03 or bd-eth02) with multi-hop flow installation."""
        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst
        src_switch = (src_host.get("switch") if src_host else None) or DPID_NAMES.get(datapath.id)
        if not src_switch:
            return
        src_vlan = vlan_id or (src_host.get("vlan") if src_host else 0)
        gateway_switch = "dist_branch" if src_switch in {"access_branch", "dist_branch"} else "core_hq"
        path = self.topo.shortest_path(src_switch, gateway_switch, vlan=src_vlan)
        self.logger.info("ROUTE_EXTERNAL: src=%s dst=%s src_sw=%s gw_sw=%s path=%s", src_ip, dst_ip, src_switch, gateway_switch, path)
        if not path:
            return

        # Install forward flows along path to gateway switch
        for i, sw_name in enumerate(path):
            sw_dpid = NAME_DPIDS.get(sw_name)
            if not sw_dpid or sw_dpid not in self.datapaths:
                continue
            sw_dp = self.datapaths[sw_dpid]
            sw_parser = sw_dp.ofproto_parser

            if i == len(path) - 1:
                # Gateway switch: output to firewall breakout port
                breakout_port_name = "bd-eth02" if sw_name == "dist_branch" else "core-eth03"
                out_port = self.topo.port_name_to_no.get(sw_name, {}).get(breakout_port_name)
                actions: list[Any] = []
                if sw_name == "core_hq":
                    actions.extend([
                        sw_parser.OFPActionSetField(eth_dst="00:00:00:00:00:01"),
                        sw_parser.OFPActionDecNwTtl(),
                    ])
                elif sw_name == "dist_branch":
                    actions.extend([
                        sw_parser.OFPActionDecNwTtl(),
                    ])
                if out_port:
                    actions.append(sw_parser.OFPActionOutput(out_port))
            else:
                next_sw = path[i + 1]
                out_port = self.topo.egress_port_for_next_hop(sw_name, next_sw, vlan=src_vlan)
                actions = [sw_parser.OFPActionOutput(out_port)] if out_port else []

            if not out_port:
                continue

            match_fwd = sw_parser.OFPMatch(
                vlan_vid=src_vlan | ofproto_v1_3.OFPVID_PRESENT,
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
            )
            self.add_flow(
                sw_dp,
                table_id=TABLE_FORWARDING,
                priority=220,
                match=match_fwd,
                actions=actions,
                reason=f"Multi-hop External Forward tới {sw_name} port {out_port}",
                policy="external_breakout",
                idle_timeout=180,
                src=src_ip,
                dst=dst_ip,
            )

        # Install reverse flow for traffic returning from breakout port to internal host
        dest_access_port = (src_host.get("port") if src_host else None) or (in_port if DPID_NAMES.get(datapath.id) == src_switch else None)
        rev_path = list(reversed(path))
        for i, sw_name in enumerate(rev_path):
            sw_dpid = NAME_DPIDS.get(sw_name)
            if not sw_dpid or sw_dpid not in self.datapaths:
                continue
            sw_dp = self.datapaths[sw_dpid]
            sw_parser = sw_dp.ofproto_parser

            if i == len(rev_path) - 1:
                rev_out_port = dest_access_port
                actions = [sw_parser.OFPActionPopVlan(), sw_parser.OFPActionOutput(rev_out_port)] if rev_out_port else []
            else:
                next_sw = rev_path[i + 1]
                rev_out_port = self.topo.egress_port_for_next_hop(sw_name, next_sw, vlan=src_vlan)
                actions = [sw_parser.OFPActionOutput(rev_out_port)] if rev_out_port else []

            if not rev_out_port:
                continue

            match_rev = sw_parser.OFPMatch(
                vlan_vid=src_vlan | ofproto_v1_3.OFPVID_PRESENT,
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=dst_ip,
                ipv4_dst=src_ip,
            )
            self.add_flow(
                sw_dp,
                table_id=TABLE_FORWARDING,
                priority=220,
                match=match_rev,
                actions=actions,
                reason=f"Multi-hop External Reverse tới {sw_name} port {rev_out_port}",
                policy="external_breakout_return",
                idle_timeout=180,
                src=dst_ip,
                dst=src_ip,
            )

        # Install dynamic 5-tuple return policy on Table 20
        proto, sport, dport, icmp_type = self._extract_l4_details(msg, ip_pkt)
        self._install_dynamic_return_policy(
            src_ip=src_ip,
            dst_ip=dst_ip,
            proto=proto,
            sport=sport,
            dport=dport,
            icmp_type=icmp_type,
            paths=path,
        )

        # Send initial packet from ingress switch
        first_out_port = (
            self.topo.port_name_to_no.get(src_switch, {}).get("core-eth03" if src_switch == "core_hq" else "bd-eth02")
            if len(path) == 1
            else self.topo.egress_port_for_next_hop(src_switch, path[1], vlan=src_vlan)
        )
        if first_out_port and DPID_NAMES.get(datapath.id) == src_switch:
            parser = datapath.ofproto_parser
            init_actions: list[Any] = []
            if len(path) == 1:
                if src_switch == "core_hq":
                    init_actions.extend([
                        parser.OFPActionSetField(eth_dst="00:00:00:00:00:01"),
                        parser.OFPActionDecNwTtl(),
                    ])
                elif src_switch == "dist_branch":
                    init_actions.extend([
                        parser.OFPActionDecNwTtl(),
                    ])
            else:
                # Outbound onto trunk link: frame was received untagged, push VLAN!
                init_actions.extend([
                    parser.OFPActionPushVlan(0x8100),
                    parser.OFPActionSetField(vlan_vid=src_vlan | ofproto_v1_3.OFPVID_PRESENT),
                ])
            init_actions.append(parser.OFPActionOutput(first_out_port))
            datapath.send_msg(
                parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=msg.buffer_id,
                    in_port=in_port,
                    actions=init_actions,
                    data=msg.data,
                )
            )

    def _find_host_port(self, dpid: int, host_name: str, vlan_id: int) -> int | None:
        for host_rec in self.hosts_by_ip.values():
            if host_rec.get("name") == host_name and host_rec.get("dpid") == dpid and host_rec.get("port"):
                return host_rec["port"]
        norm_name = host_name.replace("_", "-u") if ("_" in host_name and not host_name.startswith("iot_")) else host_name
        for p_no, prof in self.port_profiles[dpid].items():
            p_name = prof.get("name", "")
            if prof.get("vlan") == vlan_id and (host_name == p_name or norm_name == p_name or prof.get("host") == host_name):
                return p_no
        return None

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, event: Any) -> None:
        """Handle link failure and trigger shortest path failover between Primary and Backup."""
        msg = event.msg
        datapath = msg.datapath
        dpid = datapath.id
        switch_name = DPID_NAMES.get(dpid, "")
        port_no = msg.desc.port_no
        raw_name = getattr(msg.desc, "name", "")
        port_name = raw_name.decode("utf-8") if isinstance(raw_name, bytes) else str(raw_name)
        if getattr(msg, "reason", None) == getattr(datapath.ofproto, "OFPPR_ADD", 0):
            self.topo.register_port(switch_name, port_no, port_name)
            self._configure_port_profile(dpid, port_no, port_name)
            self._build_topology_links(dpid)
            self._install_port_pipeline_flows(datapath)
            self._write_state()
            return

        state = msg.desc.state
        link_down = (state & datapath.ofproto.OFPPS_LINK_DOWN) != 0

        self.stats["failover_count"] += 1
        new_status = "down" if link_down else "up"
        circuit_info = self.topo.set_port_link_status(switch_name, port_no, new_status)

        if circuit_info:
            u, v = circuit_info
            port_name = self.topo.switch_ports[switch_name].get(port_no, str(port_no))
            self.logger.warning("LINK STATUS CHANGE: Switch %s port %s (%s) chuyển sang %s", switch_name, port_no, port_name, new_status)

            # Check if this is the Primary L2VPN link failing over to Backup
            if "93p" in port_name and link_down:
                self.vlan93_active_circuit = "backup"
                # Activate backup circuit
                for c in self.topo.links.get(("core_hq", "dist_branch"), []):
                    if c["role"] == "backup":
                        c["status"] = "up"
                for c in self.topo.links.get(("dist_branch", "core_hq"), []):
                    if c["role"] == "backup":
                        c["status"] = "up"
                self.logger.warning("VLAN 93 FAILOVER ACTIVATED: Chuyển kênh sang Backup L2VPN (core-eth93b <-> bd-eth93b)")
                self._record_event("FAILOVER_PRIMARY_TO_BACKUP", {
                    "reason": f"Primary L2VPN port {port_name} down",
                    "switch": switch_name,
                    "backup_circuit": "l2vpn-backup",
                })
            elif "93p" in port_name and not link_down:
                self.vlan93_active_circuit = "primary"
                # Primary restored
                for c in self.topo.links.get(("core_hq", "dist_branch"), []):
                    if c["role"] == "backup":
                        c["status"] = "standby"
                self.logger.info("VLAN 93 RESTORED: Khôi phục về Primary L2VPN (core-eth93p <-> bd-eth93p)")
                self._record_event("FAILOVER_RESTORED_TO_PRIMARY", {
                    "reason": f"Primary L2VPN port {port_name} restored",
                    "switch": switch_name,
                })

            # Selective flow purge: ONLY delete flows matching VLAN 93 or the failed port in Table 30
            # Preserves all other project flows (VLAN 101, 103, 104, 110, 120, 140, 100)
            for dp in self.datapaths.values():
                p = dp.ofproto_parser
                dp.send_msg(
                    p.OFPFlowMod(
                        datapath=dp,
                        table_id=TABLE_FORWARDING,
                        command=dp.ofproto.OFPFC_DELETE,
                        out_port=dp.ofproto.OFPP_ANY,
                        out_group=dp.ofproto.OFPG_ANY,
                        match=p.OFPMatch(vlan_vid=93 | ofproto_v1_3.OFPVID_PRESENT),
                    )
                )
                if dp.id == dpid:
                    dp.send_msg(
                        p.OFPFlowMod(
                            datapath=dp,
                            table_id=TABLE_FORWARDING,
                            command=dp.ofproto.OFPFC_DELETE,
                            out_port=port_no,
                            out_group=dp.ofproto.OFPG_ANY,
                            match=p.OFPMatch(),
                        )
                    )
                # Re-install Table 30 Miss so subsequent packets go to Controller
                actions = [p.OFPActionOutput(dp.ofproto.OFPP_CONTROLLER, dp.ofproto.OFPCML_NO_BUFFER)]
                self.add_flow(
                    dp,
                    table_id=TABLE_FORWARDING,
                    priority=0,
                    match=p.OFPMatch(),
                    actions=actions,
                    reason="Table 30 Miss: Gói đầu tiên kích hoạt controller cài đặt multi-hop path",
                    policy="forwarding_first_packet",
                    idle_timeout=0,
                )
            self._write_state()
