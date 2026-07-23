from pathlib import Path

from scripts.common import load_vars
from scripts.network_model import build_host_inventory, controlled_switches, load_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine


ROOT = Path(__file__).resolve().parents[1]


def test_enterprise_zones_use_unused_vlan_ids_without_overlapping_existing_plan():
    model = load_network_model()
    vlans = {int(item["id"]): item for item in load_vars()["vlans"]}
    assert {80, 100, 110}.issubset(vlans)
    assert {80, 100, 110}.isdisjoint({10, 20, 30, 40, 50, 60, 70, 90})
    assert model["host_groups"]["guest"]["vlan"] == 80
    assert model["host_groups"]["iot_ups"]["vlan"] == 110
    assert {item["id"] for item in vlans.values()} == set(vlans)


def test_enterprise_inventory_preserves_corporate_users_and_adds_zones():
    hosts = build_host_inventory(load_network_model())
    assert sum(host["kind"] == "user" for host in hosts.values()) == 110
    assert sum(host["kind"] == "service" for host in hosts.values()) == 5
    assert sum(host["kind"] in {"guest", "iot"} for host in hosts.values()) == 9
    assert sum(host["kind"] == "infrastructure_service" for host in hosts.values()) == 4
    assert len(hosts) == 128
    assert len(controlled_switches(load_network_model())) == 12


def test_enterprise_least_privilege_policy_is_directional():
    engine = PolicyEngine(ROOT / "sdn_mpls_demo" / "policy.yml")
    assert engine.decide("guest_01", "hdhcp")["action"] == "allow"
    assert engine.decide("guest_01", "hinternet")["action"] == "allow"
    assert engine.decide("guest_01", "h20_01")["action"] == "deny"
    assert engine.decide("iot_cam_01", "hmonitor")["action"] == "allow"
    assert engine.decide("iot_cam_01", "h90")["action"] == "deny"
    assert engine.decide("h70_01", "ups_core_01")["action"] == "allow"
    assert engine.decide("h70_01", "hsocial")["action"] == "deny"


def test_runtime_topology_declares_vlan_access_trunks_and_router_subinterfaces():
    source = (ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py").read_text(encoding="utf-8")
    assert "def configure_vlan_switching" in source
    assert '"access_iot": ("iot-eth99", "core-eth08", [110])' in source
    assert '"access_guest": ("gst-eth99", "core-eth09", [80])' in source
    assert '"infra_access": ("inf-eth99", "core-eth10", [100])' in source
    assert "def configure_vlan_router_interface" in source
    assert "(110, \"172.16.110.1/24\")" in source
    assert "(80, \"172.16.80.1/24\")" in source
