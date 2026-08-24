from pathlib import Path

from scripts.common import load_vars
from scripts.generate_configs import generate_configs
from scripts.network_model import build_host_inventory, controlled_switches, load_network_model
from scripts.validate_redesigned_topology import validate
from scripts.validate_vars import validate_all
from scripts.verify_network import verify_generated
from sdn_mpls_demo.policy_engine import PolicyEngine


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "sdn_mpls_demo" / "policy.yml"


def test_v7_source_of_truth_is_internally_consistent():
    model = load_network_model()
    config = load_vars()

    assert validate_all(config) == []
    assert validate() == []
    assert set(model["sites"]) == {"hq", "branch", "wan", "internet"}
    assert set(controlled_switches(model)) == {
        "access_floor1",
        "access_floor2",
        "core_hq",
        "access_branch",
        "dist_branch",
        "infra_access",
    }

    hosts = build_host_inventory(model)
    assert sum(host["kind"] == "user" for host in hosts.values()) == 90


def test_vlan93_is_l2_stretched_with_hq_gateway_only():
    model = load_network_model()
    config = load_vars()
    shared = model["host_groups"]["project_2"]
    placements = shared["placements"]

    assert shared["vlan"] == 93
    assert shared["subnet"] == "10.10.93.0/24"
    assert shared["gateway"] == "10.10.93.1"
    assert shared["gateway_site"] == "hq"
    assert {item["site"] for item in placements} == {"hq", "branch"}

    branch = next(
        device
        for device in config["sites"]["branch"]["devices"]
        if device["model_node"] == "dist_branch"
    )
    assert 93 in branch["no_svi_vlans"]
    assert 93 not in branch["svi_vlans"]

    routed = {
        route["prefix"]
        for owner in ("hq_l3_gateway", "telesale_l3_gateway")
        for route in config["routes"][owner].get("user_routes", [])
    }
    assert "10.10.93.0/24" not in routed


def test_v7_policy_paths_and_least_privilege():
    engine = PolicyEngine(POLICY)

    l2 = engine.decide("h93_11", "h93_01")
    assert l2["action"] == "allow"
    assert "l2vpn_primary" in l2["path"]
    assert "ipsec_l3" not in l2["path"]

    assert engine.decide("h101_01", "h103_01")["action"] == "deny"
    assert engine.decide("guest_01", "h93_01")["action"] == "deny"

    for service in ("hdhcp", "hdns", "had", "hfile", "hntp"):
        assert engine.decide("h101_01", service)["action"] == "allow"
    for service in ("hmonitor", "hbackup"):
        assert engine.decide("h101_01", service)["action"] == "deny"

    branch_iot = engine.decide("iot_branch_cam_01", "hmonitor")
    assert branch_iot["action"] == "allow"
    assert "ipsec_l3" in branch_iot["path"]
    assert "l2vpn_primary" not in branch_iot["path"]


def test_generated_candidate_configs_match_v7_contract(tmp_path: Path):
    rendered = {path.name for path in generate_configs(tmp_path)}
    assert {
        "hq-core-dist.cfg",
        "br-core-dist.cfg",
        "hq-ce1.cfg",
        "hq-ce2.cfg",
        "br-ce1.cfg",
        "br-ce2.cfg",
    }.issubset(rendered)
    assert verify_generated(tmp_path) == []

    hq_core = (tmp_path / "hq-core-dist.cfg").read_text(encoding="utf-8")
    branch_core = (tmp_path / "br-core-dist.cfg").read_text(encoding="utf-8")
    assert "interface Vlan93" in hq_core
    assert "ip address 10.10.93.1 255.255.255.0" in hq_core
    assert "interface Vlan93" not in branch_core

    assert "host 10.10.100.12" in hq_core
    assert "host 10.10.100.13" in hq_core
    assert "deny ip 10.10.101.0 0.0.0.255 10.10.100.0 0.0.0.255 log" in hq_core
