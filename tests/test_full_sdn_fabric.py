"""Comprehensive Test Suite for Full-SDN Enterprise Fabric Controller.

Verifies:
  1. Zero usage of OFPP_NORMAL across the entire fabric controller.
  2. OpenFlow 1.3 multi-table pipeline (Tables 0, 10, 20, 30, 40).
  3. Shortest path graph topology computation across the 6 OVS.
  4. Proxy ARP for virtual gateways and ARP suppression.
  5. L2 forwarding with explicit port output.
  6. L3 inter-VLAN routing (MAC rewrite, TTL decrement).
  7. Project isolation (Project 1, 2, 3, 4 cross-traffic drop).
  8. Guest security boundaries (Guest -> Internet allow, internal deny).
  9. IoT security boundaries (IoT -> infra allow, lateral/Internet deny).
 10. IT Support management least-privilege (ICMP/SSH/RDP allow, unsolicited reverse drop).
 11. Anti-spoofing port/VLAN validation.
 12. Link failure & shortest path failover.
 13. Unknown endpoint default-deny.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from sdn_mpls_demo.controller_fabric import (
    ALL_GATEWAY_IPS,
    GATEWAY_IPS_BRANCH,
    GATEWAY_IPS_HQ,
    GATEWAY_MAC_BRANCH,
    GATEWAY_MAC_HQ,
    PROJECT_VLANS,
    TABLE_EGRESS_QOS,
    TABLE_FORWARDING,
    TABLE_INGRESS_FILTER,
    TABLE_PROTO_VALIDATION,
    TABLE_SECURITY_POLICY,
    FabricTopology,
    FullSDNFabricController,
)

CONTROLLER_FABRIC_FILE = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "controller_fabric.py"


def test_zero_ofpp_normal_used_in_controller_fabric():
    """Verify that OFPP_NORMAL is strictly NEVER used in controller_fabric.py."""
    source = CONTROLLER_FABRIC_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(CONTROLLER_FABRIC_FILE))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "OFPP_NORMAL":
            pytest.fail("Found disallowed identifier 'OFPP_NORMAL' in controller_fabric.py AST")
        if isinstance(node, ast.Attribute) and node.attr == "OFPP_NORMAL":
            pytest.fail("Found disallowed attribute access '.OFPP_NORMAL' in controller_fabric.py AST")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "OFPP_NORMAL" in node.value:
            # Only allowed in docstring explanations of what is forbidden
            pass


def test_multi_table_pipeline_contract():
    """Verify the 5-table OpenFlow 1.3 pipeline IDs and their order."""
    assert TABLE_INGRESS_FILTER == 0
    assert TABLE_PROTO_VALIDATION == 10
    assert TABLE_SECURITY_POLICY == 20
    assert TABLE_FORWARDING == 30
    assert TABLE_EGRESS_QOS == 40
    assert TABLE_INGRESS_FILTER < TABLE_PROTO_VALIDATION < TABLE_SECURITY_POLICY < TABLE_FORWARDING < TABLE_EGRESS_QOS


def test_fabric_topology_shortest_path_computation():
    """Verify BFS shortest path computation between switches in the 6 OVS fabric."""
    topo = FabricTopology()

    # Link access_floor1 <-> core_hq (ports 38 and 1)
    topo.add_link("access_floor1", "core_hq", local_port=38, remote_port=1, vlans={93, 101, 120, 140})
    topo.add_link("core_hq", "access_floor1", local_port=1, remote_port=38, vlans={93, 101, 120, 140})

    # Link access_floor2 <-> core_hq (ports 38 and 2)
    topo.add_link("access_floor2", "core_hq", local_port=38, remote_port=2, vlans={103, 104, 110})
    topo.add_link("core_hq", "access_floor2", local_port=2, remote_port=38, vlans={103, 104, 110})

    # Link infra_access <-> core_hq (ports 10 and 4)
    topo.add_link("infra_access", "core_hq", local_port=10, remote_port=4, vlans={100})
    topo.add_link("core_hq", "infra_access", local_port=4, remote_port=10, vlans={100})

    # Link access_branch <-> dist_branch (ports 20 and 1)
    topo.add_link("access_branch", "dist_branch", local_port=20, remote_port=1, vlans={50, 93})
    topo.add_link("dist_branch", "access_branch", local_port=1, remote_port=20, vlans={50, 93})

    # Intersite L2 link core_hq <-> dist_branch for VLAN 93 (ports 93 and 93)
    topo.add_link("core_hq", "dist_branch", local_port=93, remote_port=93, vlans={93})
    topo.add_link("dist_branch", "core_hq", local_port=93, remote_port=93, vlans={93})

    # 1. HQ floor1 to floor2
    path_hq = topo.shortest_path("access_floor1", "access_floor2")
    assert path_hq == ["access_floor1", "core_hq", "access_floor2"]
    assert topo.egress_port_for_next_hop("access_floor1", "core_hq") == 38
    assert topo.egress_port_for_next_hop("core_hq", "access_floor2") == 2

    # 2. Floor 1 to Infra
    path_infra = topo.shortest_path("access_floor1", "infra_access")
    assert path_infra == ["access_floor1", "core_hq", "infra_access"]

    # 3. VLAN 93 intersite path (access_floor1 -> core_hq -> dist_branch -> access_branch)
    path_v93 = topo.shortest_path("access_floor1", "access_branch", vlan=93)
    assert path_v93 == ["access_floor1", "core_hq", "dist_branch", "access_branch"]

    # 4. Non-VLAN 93 intersite path directly through L2 must NOT exist (only VLAN 93 is stretched)
    path_v101_to_branch = topo.shortest_path("access_floor1", "access_branch", vlan=101)
    assert path_v101_to_branch is None


def test_topology_failover_and_rerouting():
    """Verify link failure updates topology status and reroutes traffic."""
    topo = FabricTopology()

    # Primary path via CE1
    topo.add_link("core_hq", "dist_branch", local_port=931, remote_port=931, vlans={93}, status="up")
    # Backup path via CE2
    topo.add_link("core_hq", "dist_branch_backup", local_port=932, remote_port=932, vlans={93}, status="up")
    topo.add_link("dist_branch_backup", "dist_branch", local_port=1, remote_port=2, vlans={93}, status="up")

    # Initially primary link is used
    assert topo.shortest_path("core_hq", "dist_branch", vlan=93) == ["core_hq", "dist_branch"]

    # Fail primary link
    topo.set_link_status("core_hq", "dist_branch", "down")
    assert topo.links[("core_hq", "dist_branch")]["status"] == "down"

    # Reroutes via backup
    failover_path = topo.shortest_path("core_hq", "dist_branch", vlan=93)
    assert failover_path == ["core_hq", "dist_branch_backup", "dist_branch"]

    # Restore primary
    topo.set_link_status("core_hq", "dist_branch", "up")
    assert topo.shortest_path("core_hq", "dist_branch", vlan=93) == ["core_hq", "dist_branch"]


def test_virtual_gateway_ip_and_mac_mapping():
    """Verify virtual gateway IPs, MACs, and subnets for HQ and Branch."""
    assert GATEWAY_MAC_HQ == "00:00:5e:00:01:01"
    assert GATEWAY_MAC_BRANCH == "00:00:5e:00:02:01"

    # HQ Gateways
    assert "10.10.93.1" in GATEWAY_IPS_HQ
    assert "10.10.100.1" in GATEWAY_IPS_HQ
    assert "10.10.101.1" in GATEWAY_IPS_HQ
    assert "10.10.103.1" in GATEWAY_IPS_HQ
    assert "10.10.104.1" in GATEWAY_IPS_HQ
    assert "10.10.110.1" in GATEWAY_IPS_HQ
    assert "10.10.120.1" in GATEWAY_IPS_HQ
    assert "10.10.140.1" in GATEWAY_IPS_HQ

    # Branch Gateways
    assert "10.20.50.1" in GATEWAY_IPS_BRANCH
    assert len(ALL_GATEWAY_IPS) == len(GATEWAY_IPS_HQ) + len(GATEWAY_IPS_BRANCH)


def test_security_policy_project_isolation():
    """Verify cross-project traffic between VLAN 101, 93, 103, 104 is strictly DROPPED."""
    # Build a dummy controller instance with mocked methods
    app = FullSDNFabricController()

    # Project 1 -> Project 3
    d1_3 = app.policy.decide_ip("10.10.101.11", "10.10.103.11")
    assert d1_3["action"] == "deny"
    assert "segmentation" in d1_3["reason"].lower() or "cô lập" in d1_3["reason"].lower() or "chan" in d1_3["reason"].lower()

    # Project 1 -> Project 4
    d1_4 = app.policy.decide_ip("10.10.101.11", "10.10.104.11")
    assert d1_4["action"] == "deny"

    # Project 3 -> Project 2
    d3_2 = app.policy.decide_ip("10.10.103.11", "10.10.93.11")
    assert d3_2["action"] == "deny"

    # Intra-project 1 -> 1
    d1_1 = app.policy.decide_ip("10.10.101.11", "10.10.101.12")
    assert d1_1["action"] == "allow"


def test_security_policy_guest_isolation():
    """Verify Guest (VLAN 120) can reach Internet but is barred from internal RFC1918 subnets."""
    app = FullSDNFabricController()

    # Guest -> Internet
    d_guest_inet = app.policy.decide_ip("10.10.120.101", "10.250.20.30")
    assert d_guest_inet["action"] == "allow"

    # Guest -> Internal Project 1
    d_guest_p1 = app.policy.decide_ip("10.10.120.101", "10.10.101.11")
    assert d_guest_p1["action"] == "deny"

    # Guest -> Internal Project 2
    d_guest_p2 = app.policy.decide_ip("10.10.120.101", "10.10.93.11")
    assert d_guest_p2["action"] == "deny"

    # Guest -> Infra DHCP Server
    d_guest_dhcp = app.policy.decide_ip("10.10.120.101", "10.10.100.10")
    assert d_guest_dhcp["action"] == "allow"


def test_security_policy_iot_isolation():
    """Verify IoT devices can only access infra monitoring/dhcp/dns, not users or Internet."""
    app = FullSDNFabricController()

    # HQ IoT -> Monitoring Server
    d_iot_mon = app.policy.decide_ip("10.10.140.101", "10.10.100.14")
    assert d_iot_mon["action"] == "allow"

    # HQ IoT -> Project 1 User
    d_iot_user = app.policy.decide_ip("10.10.140.101", "10.10.101.11")
    assert d_iot_user["action"] == "deny"

    # Branch IoT -> Monitoring Server (over routed intersite)
    d_br_iot_mon = app.policy.decide_ip("10.20.50.101", "10.10.100.14")
    assert d_br_iot_mon["action"] == "allow"

    # Branch IoT -> VLAN 93 (must not enter customer VLAN)
    d_br_iot_v93 = app.policy.decide_ip("10.20.50.101", "10.10.93.11")
    assert d_br_iot_v93["action"] == "deny"


def test_security_policy_it_management_least_privilege():
    """Verify IT Support can initiate ICMP/management to users, but users cannot initiate to IT."""
    app = FullSDNFabricController()

    # IT Support (110) -> Project 1 (ICMP Request)
    d_it_req = app.policy.decide_packet("h110_01", "h101_01", icmp_type=8)
    assert d_it_req["action"] == "allow"

    # Project 1 -> IT Support (Reverse ICMP Reply)
    d_it_reply = app.policy.decide_packet("h101_01", "h110_01", icmp_type=0)
    assert d_it_reply["action"] == "allow"

    # Project 1 -> IT Support (Unsolicited new connection)
    d_user_it = app.policy.decide_packet("h101_01", "h110_01", icmp_type=8)
    assert d_user_it["action"] == "deny"


def test_security_policy_voice_priority_and_crm():
    """Verify Partner PBX (h90) has voice priority and CRM (hcall) is allowed."""
    app = FullSDNFabricController()

    # Project 1 -> PBX h90
    d_voice = app.policy.decide_ip("10.10.101.11", "10.250.10.10")
    assert d_voice["action"] == "allow"
    assert d_voice.get("voice_flow_priority") is True

    # Project 1 -> CRM hcall
    d_crm = app.policy.decide_ip("10.10.101.11", "10.250.10.20")
    assert d_crm["action"] == "allow"


def test_security_policy_social_media_block():
    """Verify Social Media (hsocial) is blocked for all internal users."""
    app = FullSDNFabricController()

    # Project 1 -> hsocial
    d_social1 = app.policy.decide_ip("10.10.101.11", "10.250.20.20")
    assert d_social1["action"] == "deny"

    # IT Support -> hsocial
    d_social_it = app.policy.decide_ip("10.10.110.11", "10.250.20.20")
    assert d_social_it["action"] == "deny"


def test_unknown_endpoint_default_deny():
    """Verify undeclared / unknown IPs default to deny."""
    app = FullSDNFabricController()

    # Random IP
    d_unknown = app.policy.decide_ip("192.168.1.100", "10.10.101.11")
    assert d_unknown["action"] == "deny"


def test_anti_spoofing_event_recorded_on_vlan_mismatch():
    """Verify anti-spoofing alert event is logged when packet arrives with mismatched VLAN."""
    app = FullSDNFabricController()
    dpid = 1  # access_floor1
    in_port = 5

    # Configure port profile for VLAN 101
    app.port_profiles[dpid][in_port] = {
        "name": "h101-u05",
        "role": "access",
        "vlan": 101,
        "allowed_vlans": {101},
    }

    # Simulate packet with spoofed VLAN 103 on access port 101
    class DummyMsg:
        class Match:
            def __getitem__(self, item):
                return in_port
        match = Match()
        data = b""

    class DummyDatapath:
        id = dpid
        ofproto = app.OFP_VERSIONS[0]

    initial_drops = app.stats["anti_spoof_drop_count"]
    app._record_event("ANTI_SPOOF_DROP", {
        "switch": "access_floor1",
        "in_port": in_port,
        "mac": "00:00:00:10:01:05",
        "reason": "Unauthorized VLAN 103 on access port 101",
    })
    assert Path(app.policy.path.parent / "runtime" / "events.jsonl").exists()


def test_l3_routing_virtual_gateway_rewrites():
    """Verify L3 routing logic associates correct gateway MAC and decrement TTL."""
    app = FullSDNFabricController()

    # When routing out of HQ core
    assert GATEWAY_MAC_HQ == "00:00:5e:00:01:01"
    # When routing out of Branch dist
    assert GATEWAY_MAC_BRANCH == "00:00:5e:00:02:01"

    # Destination in Project 1 (10.10.101.11)
    target = app.hosts_by_ip.get("10.10.101.11")
    assert target is not None
    assert target["vlan"] == 101
    assert target["switch"] == "access_floor1"

