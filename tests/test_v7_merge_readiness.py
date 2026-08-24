from pathlib import Path

from scripts.common import load_vars
from scripts.generate_configs import generate_configs
from scripts.network_model import build_host_inventory, controlled_switches, load_network_model
from scripts.validate_redesigned_topology import validate
from scripts.validate_vars import validate_all
from scripts.verify_network import verify_generated
from sdn_mpls_demo.firewall_nftables import build_firewall_plans, render_nftables_ruleset
from sdn_mpls_demo.policy_engine import PolicyEngine
from sdn_mpls_demo.runtime_contract import source_truth_runtime_links


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
    assert sum(host["kind"] == "user" for host in build_host_inventory(model).values()) == 90


def test_vlan93_is_l2_stretched_with_hq_gateway_only():
    model = load_network_model()
    config = load_vars()
    shared = model["host_groups"]["project_2"]

    assert shared["vlan"] == 93
    assert shared["subnet"] == "10.10.93.0/24"
    assert shared["gateway"] == "10.10.93.1"
    assert shared["gateway_site"] == "hq"
    assert {item["site"] for item in shared["placements"]} == {"hq", "branch"}

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


def test_ipsec_abstraction_terminates_on_firewalls():
    model = load_network_model()
    config = load_vars()

    assert model["edge_design"]["ipsec"]["runtime_path"] == ["fw_hq", "ipsec_l3", "fw_telesale"]
    declared = {frozenset((left, right)) for left, right, kind in model["links"] if kind == "routed"}
    assert frozenset(("fw_hq", "ipsec_l3")) in declared
    assert frozenset(("ipsec_l3", "fw_telesale")) in declared
    assert frozenset(("core_hq", "ipsec_l3")) not in declared
    assert frozenset(("dist_branch", "ipsec_l3")) not in declared

    link_names = set(config["links"])
    assert "fw_hq_to_ipsec" in link_names
    assert "ipsec_to_fw_branch" in link_names
    assert "hq_l3_to_ipsec" not in link_names
    assert "ipsec_to_branch_l3" not in link_names
    source_truth_runtime_links(model)


def test_firewall_runtime_enforces_declared_tunnel_prefixes():
    plans = build_firewall_plans()
    hq = plans["fw_hq"]
    branch = plans["fw_telesale"]

    assert hq["tunnel_interface"] == "fw_hq-eth2"
    assert hq["remote_subnets"] == ("10.20.50.0/24",)
    assert branch["tunnel_interface"] == "fw_tel-eth2"
    assert "10.10.93.0/24" not in branch["remote_subnets"]
    assert set(branch["remote_subnets"]) == {
        "10.10.100.0/24",
        "10.10.101.0/24",
        "10.10.103.0/24",
        "10.10.104.0/24",
        "10.10.110.0/24",
        "10.10.120.0/24",
        "10.10.140.0/24",
    }
    for plan in (hq, branch):
        ruleset = render_nftables_ruleset(plan)
        assert "allow-ipsec-overlay-out" in ruleset
        assert "allow-ipsec-overlay-in" in ruleset
        assert "forward-default-deny" in ruleset


def test_provider_circuits_are_site_local():
    circuits = load_network_model()["edge_design"]["provider_domain"]["circuits"]
    assert set(circuits) == {"hq_primary", "hq_backup", "branch_primary", "branch_backup"}
    assert circuits["hq_primary"]["sites"] == ["hq"]
    assert circuits["hq_backup"]["sites"] == ["hq"]
    assert circuits["branch_primary"]["sites"] == ["branch"]
    assert circuits["branch_backup"]["sites"] == ["branch"]
    assert len({item["id"] for item in circuits.values()}) == 4


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
    assert branch_iot["path"] == [
        "iot_branch",
        "access_branch",
        "dist_branch",
        "fw_telesale",
        "ipsec_l3",
        "fw_hq",
        "core_hq",
        "infra_access",
        "hmonitor",
    ]


def test_generated_candidate_configs_match_v7_contract(tmp_path: Path):
    rendered = {path.name for path in generate_configs(tmp_path)}
    assert {
        "hq-core-dist.cfg",
        "br-core-dist.cfg",
        "hq-ce1.cfg",
        "hq-ce2.cfg",
        "br-ce1.cfg",
        "br-ce2.cfg",
        "hq-firewall-ha.policy.txt",
        "br-firewall-ha.policy.txt",
    }.issubset(rendered)
    assert verify_generated(tmp_path) == []

    hq_core = (tmp_path / "hq-core-dist.cfg").read_text(encoding="utf-8")
    branch_core = (tmp_path / "br-core-dist.cfg").read_text(encoding="utf-8")
    assert "interface Vlan93" in hq_core
    assert "ip address 10.10.93.1 255.255.255.0" in hq_core
    assert "ip helper-address 10.10.100.10" in hq_core
    assert "interface Vlan93" not in branch_core
    assert "interface Vlan50" in branch_core
    assert "ip helper-address 10.10.100.10" in branch_core
    assert "Port-channel" not in hq_core
    assert "Port-channel" not in branch_core
    assert "ACL_GUEST_IN" in hq_core
    assert "ACL_IOT_HQ_IN" in hq_core
    assert "host 10.10.100.12" in hq_core
    assert "host 10.10.100.13" in hq_core
    assert "deny ip 10.10.101.0 0.0.0.255 10.10.0.0 0.0.255.255 log" in hq_core

    for name in ("hq-firewall-ha.policy.txt", "br-firewall-ha.policy.txt"):
        policy = (tmp_path / name).read_text(encoding="utf-8")
        assert "tunnel:" in policy
        assert "allow-corporate-ipsec-overlay" in policy
