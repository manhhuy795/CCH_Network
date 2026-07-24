from __future__ import annotations

from pathlib import Path

import yaml

from dashboard.backend.app import live_mininet
from scripts.network_model import controlled_switches, controller_dpid_name_map, enforcement_switch_for_group, load_network_model, runtime_switch_map
from sdn_mpls_demo.policy_engine import POLICY_FLOW_PROFILES, PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "vars" / "network_model.yml"
POLICY_PATH = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
CONTROLLER_PATH = REPO_ROOT / "sdn_mpls_demo" / "controller_policy.py"
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"
EXPECTED_CONTROLLER_TARGETS = {
    "access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2", "core_hq",
    "access_branch", "dist_branch", "infra_access",
}


def load_engine() -> PolicyEngine:
    return PolicyEngine(POLICY_PATH)


def test_phase43_controller_target_set_dpids_and_runtime_alias_are_exact():
    model = load_network_model(MODEL_PATH)
    assert set(controlled_switches(model)) == EXPECTED_CONTROLLER_TARGETS
    assert set(controller_dpid_name_map(model).values()) == EXPECTED_CONTROLLER_TARGETS
    assert len(controller_dpid_name_map(model)) == 8
    assert set(runtime_switch_map(model)) == EXPECTED_CONTROLLER_TARGETS
    assert set(runtime_switch_map(model).values()) == EXPECTED_CONTROLLER_TARGETS
    assert {model["switches"][name]["dpid"] for name in EXPECTED_CONTROLLER_TARGETS} == {
        f"000000000000000{i}" for i in range(1, 9)
    }

    excluded = {"service_net", "ce_hq", "ce_telesale", "fw_hq", "fw_telesale", "mpls_primary", "mpls_backup", "internet_zone", "h90"}
    assert not EXPECTED_CONTROLLER_TARGETS.intersection(excluded)


def test_phase43_directional_branch_isolation_uses_distribution_edge():
    engine = load_engine()
    telesale = engine.decide("h50_01", "h60_01")
    backoffice = engine.decide("h60_01", "h50_01")
    assert telesale["action"] == backoffice["action"] == "deny"
    assert telesale["blocked_at"] == telesale["enforcement_point"] == "dist_branch"
    assert backoffice["blocked_at"] == backoffice["enforcement_point"] == "core_hq"


def test_phase43_project_isolation_remains_bidirectional_at_core_hq():
    engine = load_engine()
    endpoints = {"project_a": "h20_01", "project_b": "h30_01", "project_c": "h40_01"}
    for source_group, source in endpoints.items():
        for destination_group, destination in endpoints.items():
            if source_group == destination_group:
                continue
            decision = engine.decide(source, destination)
            assert decision["action"] == "deny"
            assert decision["blocked_at"] == decision["enforcement_point"] == "core_hq"
            assert decision["path"][-1] == "core_hq"


def test_phase43_voice_and_internet_paths_match_two_site_design():
    engine = load_engine()
    assert engine.decide("h60_01", "h90")["path"] == ["backoffice", "access_floor2", "dist_hq_2", "core_hq", "infra_access", "h90"]
    assert engine.decide("h50_01", "h90")["path"] == [
        "telesale", "access_branch", "dist_branch", "ce_telesale", "mpls_primary", "ce_hq", "core_hq", "infra_access", "h90"
    ]
    assert engine.decide("h60_01", "hzalo")["path"][-3:] == ["fw_hq", "internet_zone", "hzalo"]
    assert engine.decide("h50_01", "hzalo")["path"][-3:] == ["fw_telesale", "internet_zone", "hzalo"]


def test_phase43_isolation_flow_specs_have_exact_match_cookie_priority_and_placement():
    specs = load_engine().isolation_flow_specs()
    assert len(specs) == len({(item["source_group"], item["destination_group"]) for item in specs}) == 8
    assert {spec["switch"] for spec in specs} == {"core_hq", "dist_branch"}
    assert all(spec["action"] == "DROP" and spec["priority"] == 400 for spec in specs)
    project_drop = next(spec for spec in specs if spec["source_group"] == "project_a" and spec["destination_group"] == "project_b")
    assert project_drop["cookie"] == 0x1001
    assert project_drop["match"] == {"eth_type": "ipv4", "ipv4_src": "172.16.20.0/24", "ipv4_dst": "172.16.30.0/24"}
    branch_drop = next(spec for spec in specs if spec["source_group"] == "telesale" and spec["destination_group"] == "backoffice")
    assert branch_drop["switch"] == "dist_branch"
    assert branch_drop["cookie"] == 0x1002


def test_phase43_policy_reload_plan_is_stable_and_cookie_reconciled():
    first = load_engine().isolation_flow_identities()
    second = load_engine().isolation_flow_identities()
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    assert first == second
    assert len(first) == len(set(first)) == 8
    assert "self._delete_cookie(datapath, cookie)" in controller
    assert "cookie_mask=0xFFFFFFFFFFFFFFFF" in controller
    assert POLICY_FLOW_PROFILES["telesale_backoffice_isolation"] == {"cookie": 0x1002, "priority": 400, "action": "DROP"}


def test_phase43_arp_transit_does_not_bypass_ipv4_policy():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    method = controller.split("def install_arp_transit_flow", 1)[1].split("@set_ev_cls", 1)[0]
    assert "parser.OFPMatch(eth_type=ether_types.ETH_TYPE_ARP)" in method
    assert "parser.OFPActionOutput(normal_port)" in method
    assert "ipv4_src" not in method and "ipv4_dst" not in method


def test_phase43_dashboard_exposes_new_logical_ids_and_no_old_shared_switch():
    payload = live_mininet.topology_payload()
    logical_ids = {str(node["id"]) for node in payload["nodes"]}
    assert EXPECTED_CONTROLLER_TARGETS.issubset(logical_ids)
    assert {"access_hq_a", "access_backoffice", "voice_access", "mpls_cloud"}.isdisjoint(logical_ids)
    assert set(live_mininet.CONTROLLED_SWITCHES) == EXPECTED_CONTROLLER_TARGETS


def test_phase43_policy_keys_and_enforcement_are_free_of_retired_branch_assumptions():
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    assert policy["runtime"]["controller"] == "127.0.0.1:6653"
    assert "core_hq" in policy["metadata"]["enforcement_note"]
    assert "dist_branch" in policy["metadata"]["enforcement_note"]
    policy_text = POLICY_PATH.read_text(encoding="utf-8")
    for retired in ("access_hq_a", "access_backoffice", "voice_access", "mpls_cloud", "dist_telesale"):
        assert retired not in policy_text
    assert enforcement_switch_for_group(load_network_model(MODEL_PATH), "telesale") == "dist_branch"
