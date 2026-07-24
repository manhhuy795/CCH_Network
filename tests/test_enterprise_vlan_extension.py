from pathlib import Path

from scripts.common import load_vars
from scripts.network_model import build_host_inventory, controlled_switches, load_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine


ROOT = Path(__file__).resolve().parents[1]


def test_enterprise_zones_use_site_local_vlan_ids():
    model = load_network_model()
    vlans = {int(item["id"]): item for item in load_vars()["vlans"]}
    assert {110, 111, 120}.issubset(vlans)
    assert model["host_groups"]["guest"]["vlan"] == 120
    assert model["host_groups"]["iot_hq"]["vlan"] == 110
    assert model["host_groups"]["iot_branch"]["vlan"] == 111
    assert model["host_groups"]["iot_hq"]["site"] == "hq"
    assert model["host_groups"]["iot_branch"]["site"] == "branch_telesale"


def test_enterprise_inventory_preserves_users_and_adds_zones():
    hosts = build_host_inventory(load_network_model())
    assert sum(host["kind"] == "user" for host in hosts.values()) == 110
    assert sum(host["kind"] == "service" for host in hosts.values()) == 5
    assert sum(host["kind"] in {"guest", "iot"} for host in hosts.values()) == 9
    assert sum(host["kind"] == "infrastructure_service" for host in hosts.values()) == 9
    assert len(hosts) == 133
    assert len(controlled_switches(load_network_model())) == 8


def test_enterprise_least_privilege_policy_is_directional():
    engine = PolicyEngine(ROOT / "sdn_mpls_demo" / "policy.yml")
    assert engine.decide("guest_01", "hdhcp")["action"] == "allow"
    assert engine.decide("guest_01", "hinternet")["action"] == "allow"
    assert engine.decide("guest_01", "h20_01")["action"] == "deny"
    assert engine.decide("iot_cam_01", "hmonitor")["action"] == "allow"
    assert engine.decide("iot_cam_01", "h90")["action"] == "deny"
    assert engine.decide("iot_branch_cam_01", "hmonitor")["action"] == "allow"
    assert engine.decide("h70_01", "hsocial")["action"] == "deny"


def test_runtime_topology_declares_new_trunks_and_router_subinterfaces():
    source = (ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py").read_text(encoding="utf-8")
    assert "def configure_vlan_switching" in source
    assert '"access_floor1": ("f1-eth99", "d1-eth01", [20, 30, 110, 120])' in source
    assert '"access_floor2": ("f2-eth99", "d2-eth01", [30, 40, 60, 70])' in source
    assert 'switches["access_branch"].cmd("ovs-vsctl set port br-eth99 vlan_mode=trunk trunks=50,111")' in source
    assert "(110, \"172.16.110.1/24\")" in source
    assert "(111, \"172.16.111.1/24\")" in source
    assert "core-eth03 vlan_mode=trunk" in source
