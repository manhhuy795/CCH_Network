"""Comprehensive Runtime-Grade Test Suite for Full-SDN Fabric Controller.

Verifies:
  1. Strict Zero OFPP_NORMAL across controller_fabric.py.
  2. Multi-table flow-through: Table 0 GotoTable(10), Table 10 GotoTable(20), Table 20 GotoTable(30).
  3. Multi-hop path flow installation: forward and reverse flows installed on ALL switches in path.
  4. Real L2VPN failover: Primary (core-eth93p <-> bd-eth93p) and Backup (core-eth93b <-> bd-eth93b).
  5. L3 routing FlowMod: set eth_src, set eth_dst, dec_ttl, output.
  6. Anti-spoofing enforcement: Port <-> VLAN <-> MAC <-> IP binding drop.
  7. Flow-level voice priority (Table 20 -> Table 30 without fake queues).
  8. Project isolation and guest boundaries.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from sdn_mpls_demo.controller_fabric import (
    ALL_GATEWAY_IPS,
    GATEWAY_IPS_BRANCH,
    GATEWAY_IPS_HQ,
    GATEWAY_MAC_BRANCH,
    GATEWAY_MAC_HQ,
    PROJECT_VLANS,
    TABLE_FORWARDING,
    TABLE_INGRESS_FILTER,
    TABLE_PROTO_VALIDATION,
    TABLE_SECURITY_POLICY,
    FabricTopology,
    FullSDNFabricController,
)

CONTROLLER_FABRIC_FILE = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "controller_fabric.py"


class MockParser:
    def OFPMatch(self, **kwargs):
        return dict(kwargs)

    def OFPInstructionGotoTable(self, table_id):
        return {"type": "GOTO_TABLE", "table_id": table_id}

    def OFPInstructionActions(self, type_, actions):
        return {"type": "APPLY_ACTIONS", "actions": actions}

    def OFPActionOutput(self, port, max_len=None):
        return {"action": "OUTPUT", "port": port}

    def OFPActionSetField(self, **kwargs):
        return {"action": "SET_FIELD", **kwargs}

    def OFPActionDecNwTtl(self):
        return {"action": "DEC_NW_TTL"}

    def OFPFlowMod(self, **kwargs):
        return kwargs

    def OFPPacketOut(self, **kwargs):
        return kwargs


class MockOfproto:
    OFP_VERSION = 4
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


class MockDatapath:
    def __init__(self, dpid: int):
        self.id = dpid
        self.ofproto = MockOfproto()
        self.ofproto_parser = MockParser()
        self.sent_msgs: list[dict[str, Any]] = []

    def send_msg(self, msg: Any) -> None:
        self.sent_msgs.append(msg)


def test_zero_ofpp_normal_in_controller_fabric():
    """Verify that OFPP_NORMAL is strictly NEVER referenced or used in controller_fabric.py."""
    source = CONTROLLER_FABRIC_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CONTROLLER_FABRIC_FILE))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "OFPP_NORMAL":
            pytest.fail("Found disallowed identifier 'OFPP_NORMAL' in controller_fabric.py AST")
        if isinstance(node, ast.Attribute) and node.attr == "OFPP_NORMAL":
            pytest.fail("Found disallowed attribute access '.OFPP_NORMAL' in controller_fabric.py AST")


def test_table_pipeline_ids_and_sequence():
    """Verify the 4-table pipeline structure (0 -> 10 -> 20 -> 30)."""
    assert TABLE_INGRESS_FILTER == 0
    assert TABLE_PROTO_VALIDATION == 10
    assert TABLE_SECURITY_POLICY == 20
    assert TABLE_FORWARDING == 30
    assert TABLE_INGRESS_FILTER < TABLE_PROTO_VALIDATION < TABLE_SECURITY_POLICY < TABLE_FORWARDING


def test_table_0_and_10_multi_table_flow_installation():
    """Verify Table 0 installs GotoTable(10) and Table 10 installs GotoTable(20) for legitimate traffic."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)  # access_floor1
    app.datapaths[1] = dp

    # Register access port h101-u01
    port_no = 1
    app.topo.register_port("access_floor1", port_no, "h101-u01")
    app._configure_port_profile(1, port_no, "h101-u01")
    app._install_port_pipeline_flows(dp)

    # Inspect messages sent to datapath
    flow_mods = [m for m in dp.sent_msgs if isinstance(m, dict) and "table_id" in m]

    # 1. Must find Table 0 -> GotoTable(10)
    t0_goto_t10 = [
        f for f in flow_mods
        if f.get("table_id") == TABLE_INGRESS_FILTER
        and any(inst.get("type") == "GOTO_TABLE" and inst.get("table_id") == TABLE_PROTO_VALIDATION for inst in f.get("instructions", []))
    ]
    assert len(t0_goto_t10) >= 1, "Table 0 must install GotoTable(10) flow for access port"

    # 2. Must find Table 10 -> GotoTable(20) for legitimate subnet
    t10_goto_t20 = [
        f for f in flow_mods
        if f.get("table_id") == TABLE_PROTO_VALIDATION
        and any(inst.get("type") == "GOTO_TABLE" and inst.get("table_id") == TABLE_SECURITY_POLICY for inst in f.get("instructions", []))
    ]
    assert len(t10_goto_t20) >= 1, "Table 10 must install GotoTable(20) flow for legitimate subnet"

    # 3. Must find Table 10 anti-spoof DROP rule for unauthorized IPs on this port
    t10_spoof_drop = [
        f for f in flow_mods
        if f.get("table_id") == TABLE_PROTO_VALIDATION
        and f.get("priority") == 100
        and not f.get("instructions")
    ]
    assert len(t10_spoof_drop) >= 1, "Table 10 must install proactive DROP for spoofed IPs"


def test_table_20_goto_table_30_flow_through():
    """Verify Table 20 installs GotoTable(30) for allowed intra-project and permitted services."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)  # access_floor1
    app.datapaths[1] = dp

    app._install_proactive_security_flows(dp)

    flow_mods = [m for m in dp.sent_msgs if isinstance(m, dict) and "table_id" in m]

    # Find Table 20 -> GotoTable(30) for permitted flows
    t20_goto_t30 = [
        f for f in flow_mods
        if f.get("table_id") == TABLE_SECURITY_POLICY
        and any(inst.get("type") == "GOTO_TABLE" and inst.get("table_id") == TABLE_FORWARDING for inst in f.get("instructions", []))
    ]
    assert len(t20_goto_t30) >= 5, "Table 20 must install GotoTable(30) for allowed flows"


def test_multi_hop_path_flows_installed_on_all_switches():
    """Verify that when a packet triggers routing, flow rules are installed on ALL switches in the path."""
    app = FullSDNFabricController()

    # Set up 3 switches on the path: access_floor1 (1) -> core_hq (3) -> access_floor2 (2)
    dp_f1 = MockDatapath(dpid=1)
    dp_core = MockDatapath(dpid=3)
    dp_f2 = MockDatapath(dpid=2)

    app.datapaths[1] = dp_f1
    app.datapaths[3] = dp_core
    app.datapaths[2] = dp_f2

    # Set up ports and links
    app.topo.register_port("access_floor1", 1, "h101-u01")
    app.topo.register_port("access_floor1", 38, "f1-eth99")
    app.topo.register_port("core_hq", 1, "core-eth01")
    app.topo.register_port("core_hq", 2, "core-eth02")
    app.topo.register_port("access_floor2", 38, "f2-eth99")
    app.topo.register_port("access_floor2", 1, "h103-u01")

    app.port_profiles[1][1] = {"name": "h101-u01", "role": "access", "vlan": 101}
    app.port_profiles[1][38] = {"name": "f1-eth99", "role": "trunk", "allowed_vlans": {93, 101, 120, 140}}
    app.port_profiles[3][1] = {"name": "core-eth01", "role": "trunk", "allowed_vlans": {93, 101, 120, 140}}
    app.port_profiles[3][2] = {"name": "core-eth02", "role": "trunk", "allowed_vlans": {103, 104, 110}}
    app.port_profiles[2][38] = {"name": "f2-eth99", "role": "trunk", "allowed_vlans": {103, 104, 110}}
    app.port_profiles[2][1] = {"name": "h103-u01", "role": "access", "vlan": 103}

    app.topo.add_link("access_floor1", "core_hq", local_port=38, remote_port=1, vlans={101, 103, 110})
    app.topo.add_link("core_hq", "access_floor1", local_port=1, remote_port=38, vlans={101, 103, 110})
    app.topo.add_link("core_hq", "access_floor2", local_port=2, remote_port=38, vlans={101, 103, 110})
    app.topo.add_link("access_floor2", "core_hq", local_port=38, remote_port=2, vlans={101, 103, 110})

    # Host inventory records
    app.hosts_by_ip["10.10.110.11"] = {
        "name": "h110_01",
        "ip": "10.10.110.11",
        "mac": "00:00:00:10:10:11",
        "switch": "access_floor2",
        "port": 1,
        "vlan": 110,
    }
    app.hosts_by_ip["10.10.101.11"] = {
        "name": "h101_01",
        "ip": "10.10.101.11",
        "mac": "00:00:00:10:01:11",
        "switch": "access_floor1",
        "port": 1,
        "vlan": 101,
    }

    # Simulate IT Support (access_floor2) sending ICMP to Project 1 (access_floor1)
    class DummyEthernet:
        src = "00:00:00:10:10:11"
        dst = GATEWAY_MAC_HQ

    class DummyIPv4:
        src = "10.10.110.11"
        dst = "10.10.101.11"

    class DummyMsg:
        buffer_id = 0xFFFFFFFF
        data = b"test"

    app._route_multi_hop_internal(
        dp_f2,
        in_port=1,
        eth=DummyEthernet(),
        ip_pkt=DummyIPv4(),
        src_vlan=110,
        src_host=app.hosts_by_ip["10.10.110.11"],
        dst_host=app.hosts_by_ip["10.10.101.11"],
        msg=DummyMsg(),
    )

    # 1. Verify FlowMod installed on access_floor2 (ingress switch)
    f2_flows = [m for m in dp_f2.sent_msgs if isinstance(m, dict) and m.get("table_id") == TABLE_FORWARDING]
    assert len(f2_flows) >= 2, "access_floor2 must receive both forward and reverse FlowMods"

    # 2. Verify FlowMod installed on core_hq (intermediate gateway switch)
    core_flows = [m for m in dp_core.sent_msgs if isinstance(m, dict) and m.get("table_id") == TABLE_FORWARDING]
    assert len(core_flows) >= 2, "core_hq must receive both forward and reverse FlowMods"

    # 3. Verify FlowMod installed on access_floor1 (egress switch)
    f1_flows = [m for m in dp_f1.sent_msgs if isinstance(m, dict) and m.get("table_id") == TABLE_FORWARDING]
    assert len(f1_flows) >= 2, "access_floor1 must receive both forward and reverse FlowMods"


def test_l3_routing_actions_in_core_switch():
    """Verify that the L3 gateway switch rewrites eth_src to gateway MAC, eth_dst to host MAC, and decrements TTL."""
    app = FullSDNFabricController()
    dp_core = MockDatapath(dpid=3)
    app.datapaths[3] = dp_core

    app.topo.register_port("core_hq", 1, "core-eth01")
    app.topo.register_port("core_hq", 2, "core-eth02")
    app.port_profiles[3][1] = {"name": "core-eth01", "role": "trunk", "allowed_vlans": {101, 110}}
    app.port_profiles[3][2] = {"name": "core-eth02", "role": "trunk", "allowed_vlans": {101, 110}}

    app.topo.add_link("core_hq", "access_floor1", local_port=1, remote_port=38, vlans={101, 110})
    app.topo.add_link("access_floor1", "core_hq", local_port=38, remote_port=1, vlans={101, 110})
    app.topo.add_link("core_hq", "access_floor2", local_port=2, remote_port=38, vlans={101, 110})
    app.topo.add_link("access_floor2", "core_hq", local_port=38, remote_port=2, vlans={101, 110})

    # Trigger internal routing via core_hq
    class DummyEthernet:
        src = "00:00:00:10:10:11"
        dst = GATEWAY_MAC_HQ

    class DummyIPv4:
        src = "10.10.110.11"
        dst = "10.10.101.11"

    app._route_multi_hop_internal(
        dp_core,
        in_port=2,
        eth=DummyEthernet(),
        ip_pkt=DummyIPv4(),
        src_vlan=110,
        src_host={"name": "h110_01", "mac": "00:00:00:10:10:11", "port": 1, "switch": "access_floor2", "vlan": 110},
        dst_host={"name": "h101_01", "mac": "00:00:00:10:01:11", "port": 1, "switch": "access_floor1", "vlan": 101},
        msg=type("Msg", (), {"buffer_id": 0xFFFFFFFF, "data": b""})(),
    )

    core_flows = [m for m in dp_core.sent_msgs if isinstance(m, dict) and m.get("table_id") == TABLE_FORWARDING]
    forward_flows = [m for m in core_flows if m.get("match", {}).get("ipv4_src") == "10.10.110.11"]
    assert len(forward_flows) >= 1
    forward_flow = forward_flows[0]

    # Verify action components
    actions = [inst["actions"] for inst in forward_flow["instructions"] if inst.get("type") == "APPLY_ACTIONS"][0]
    action_types = [a.get("action") for a in actions]

    assert "SET_FIELD" in action_types, "L3 flow must contain SET_FIELD actions for MAC rewrite"
    assert "DEC_NW_TTL" in action_types, "L3 flow must decrement TTL"
    assert "OUTPUT" in action_types, "L3 flow must output to next-hop port"

    # Check rewritten MAC values
    set_fields = [a for a in actions if a.get("action") == "SET_FIELD"]
    src_rewrites = [s.get("eth_src") for s in set_fields if "eth_src" in s]
    dst_rewrites = [s.get("eth_dst") for s in set_fields if "eth_dst" in s]

    assert src_rewrites == [GATEWAY_MAC_HQ], "L3 rewrite must set eth_src to GATEWAY_MAC_HQ"
    assert dst_rewrites == ["00:00:00:10:01:11"], "L3 rewrite must set eth_dst to target host MAC"


def test_real_primary_and_backup_failover_logic():
    """Verify failover switches traffic between real primary (core-eth93p) and backup (core-eth93b)."""
    topo = FabricTopology()

    # Register switches & real ports
    topo.register_port("core_hq", 931, "core-eth93p")
    topo.register_port("core_hq", 932, "core-eth93b")
    topo.register_port("dist_branch", 931, "bd-eth93p")
    topo.register_port("dist_branch", 932, "bd-eth93b")

    # Add real Primary L2VPN link
    topo.add_link("core_hq", "dist_branch", local_port=931, remote_port=931, circuit_id="l2vpn-primary", role="primary", status="up", vlans={93})
    topo.add_link("dist_branch", "core_hq", local_port=931, remote_port=931, circuit_id="l2vpn-primary", role="primary", status="up", vlans={93})

    # Add real Backup L2VPN link
    topo.add_link("core_hq", "dist_branch", local_port=932, remote_port=932, circuit_id="l2vpn-backup", role="backup", status="standby", vlans={93})
    topo.add_link("dist_branch", "core_hq", local_port=932, remote_port=932, circuit_id="l2vpn-backup", role="backup", status="standby", vlans={93})

    # 1. Normal state: Uses primary port 931 (core-eth93p)
    assert topo.egress_port_for_next_hop("core_hq", "dist_branch", vlan=93) == 931

    # 2. Simulate Primary link down
    topo.set_port_link_status("core_hq", 931, "down")

    # When primary is down, backup is activated
    circ = topo.active_circuit("core_hq", "dist_branch", vlan=93)
    assert circ is not None
    assert circ["circuit_id"] == "l2vpn-backup"
    assert circ["local_port"] == 932, "Must switch to real backup port core-eth93b (932)"

    # 3. Simulate Primary link restored
    topo.set_port_link_status("core_hq", 931, "up")
    circ_restored = topo.active_circuit("core_hq", "dist_branch", vlan=93)
    assert circ_restored["circuit_id"] == "l2vpn-primary"
    assert circ_restored["local_port"] == 931, "Must switch back to real primary port core-eth93p (931)"


def test_anti_spoofing_detection_and_drop(monkeypatch):
    """Verify that unauthorized VLAN tag on access port triggers anti-spoof alert and drop."""
    from sdn_mpls_demo import controller_fabric

    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)
    app.datapaths[1] = dp

    app.port_profiles[1][5] = {"name": "h101-u05", "role": "access", "vlan": 101}

    class DummyPacket:
        def get_protocol(self, proto_cls):
            if proto_cls == controller_fabric.ethernet.ethernet:
                return controller_fabric.ethernet.ethernet(src="00:00:00:10:01:05", dst="ff:ff:ff:ff:ff:ff", ethertype=0x8100)
            if proto_cls == controller_fabric.vlan.vlan:
                return controller_fabric.vlan.vlan(vid=103)
            return None

    monkeypatch.setattr(controller_fabric.packet, "Packet", lambda data: DummyPacket())

    class DummyMsg:
        datapath = dp
        match = {"in_port": 5}
        data = b""

    initial_drops = app.stats["anti_spoof_drop_count"]

    # Trigger packet_in with spoofed packet
    app.packet_in_handler(type("Event", (), {"msg": DummyMsg()})())

    # Verify drop counter incremented
    assert app.stats["anti_spoof_drop_count"] == initial_drops + 1, "Anti-spoof drop count must increment"


def test_honest_voice_flow_priority():
    """Verify Voice to PBX h90 (10.250.10.10) is given priority in Table 20 and transitions to Table 30."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)
    app.datapaths[1] = dp

    app._install_proactive_security_flows(dp)

    flow_mods = [m for m in dp.sent_msgs if isinstance(m, dict) and m.get("table_id") == TABLE_SECURITY_POLICY]

    voice_flows = [
        f for f in flow_mods
        if f.get("match", {}).get("ipv4_dst") == "10.250.10.10"
    ]
    assert len(voice_flows) == 1
    voice_flow = voice_flows[0]

    assert voice_flow.get("priority") == 430, "Voice flow must have higher priority (430)"
    instructions = voice_flow.get("instructions", [])
    assert any(inst.get("type") == "GOTO_TABLE" and inst.get("table_id") == TABLE_FORWARDING for inst in instructions), (
        "Voice flow must transition directly to Table 30 (not dropped in empty queue table)"
    )


def test_proxy_arp_response_generation():
    """Verify Proxy ARP synthesizes ARP reply for virtual gateway IP."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)
    app.datapaths[1] = dp

    initial_proxy_arps = app.stats["proxy_arp_count"]

    class DummyEthernet:
        src = "00:00:00:10:01:11"
        dst = "ff:ff:ff:ff:ff:ff"
        ethertype = 0x0806

    class DummyARP:
        opcode = 1  # Request
        src_mac = "00:00:00:10:01:11"
        src_ip = "10.10.101.11"
        dst_mac = "00:00:00:00:00:00"
        dst_ip = "10.10.101.1"  # Gateway IP!

    app._handle_arp(dp, in_port=1, eth=DummyEthernet(), arp_pkt=DummyARP(), vlan_id=101)

    assert app.stats["proxy_arp_count"] == initial_proxy_arps + 1
    assert len(dp.sent_msgs) == 1, "Must send PacketOut ARP reply"
    packet_out = dp.sent_msgs[0]
    assert packet_out["actions"][0]["port"] == 1, "ARP reply must be sent back out in_port 1"


def test_project_isolation_dataplane_flow_mods():
    """Verify Table 20 installs explicit DROP flow mods for cross-project pairs (VLAN 101, 93, 103, 104)."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)
    app.datapaths[1] = dp

    app._install_proactive_security_flows(dp)

    flow_mods = [m for m in dp.sent_msgs if isinstance(m, dict) and m.get("table_id") == TABLE_SECURITY_POLICY]
    drop_flows = [f for f in flow_mods if f.get("priority") == 400 and not f.get("instructions")]

    # For 4 project VLANs, there are 4 * 3 = 12 cross-project isolation drops
    assert len(drop_flows) == 12, "Must install exactly 12 cross-project DROP flows in Table 20"


def test_guest_isolation_dataplane_flow_mods():
    """Verify Table 20 installs DROP flows for Guest to internal subnets (10.10.0.0/16, 10.20.0.0/16)."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)
    app.datapaths[1] = dp

    app._install_proactive_security_flows(dp)

    guest_drops = [f for f in app.installed_flows if f.get("policy") == "guest_isolation" and f.get("action") == "DROP"]
    assert len(guest_drops) == 2, "Must install exactly 2 internal subnet DROP flows for Guest"


def test_iot_isolation_dataplane_flow_mods():
    """Verify Table 20 installs DROP flows for IoT lateral movement and internet."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)
    app.datapaths[1] = dp

    app._install_proactive_security_flows(dp)

    iot_drops = [f for f in app.installed_flows if f.get("policy") == "iot_isolation" and f.get("action") == "DROP"]
    assert len(iot_drops) == 2, "Must install lateral/internet DROP flows for both HQ and Branch IoT"


def test_it_support_management_dataplane_flow_mods():
    """Verify Table 20 installs allow for IT ICMP/echo-reply and drop for unsolicited user ICMP."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)
    app.datapaths[1] = dp

    app._install_proactive_security_flows(dp)

    it_unsolicited_drops = [f for f in app.installed_flows if f.get("policy") == "it_inbound_block" and f.get("action") == "DROP"]
    assert len(it_unsolicited_drops) == 6, "Must install unsolicited reverse DROP flows for all 6 managed user groups"


def test_table_20_default_deny_flow_mod():
    """Verify Table 20 has table-miss flow mod with priority 0 and empty actions (Strict Default-Deny)."""
    app = FullSDNFabricController()
    dp = MockDatapath(dpid=1)
    app.datapaths[1] = dp

    app._setup_pipeline_defaults(dp)

    flow_mods = [m for m in dp.sent_msgs if isinstance(m, dict) and m.get("table_id") == TABLE_SECURITY_POLICY]
    default_deny = [f for f in flow_mods if f.get("priority") == 0 and not f.get("instructions")]

    assert len(default_deny) == 1, "Table 20 must have a strict Default-Deny priority 0 DROP flow"

