from __future__ import annotations

from pathlib import Path

import yaml

from dashboard.backend.app import live_mininet
from scripts.network_model import (
    controlled_switches,
    controller_dpid_name_map,
    enforcement_switch_for_group,
    load_network_model,
    runtime_switch_map,
    runtime_switch_name,
)
from sdn_mpls_demo.policy_engine import POLICY_FLOW_PROFILES, PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "vars" / "network_model.yml"
POLICY_PATH = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
CONTROLLER_PATH = REPO_ROOT / "sdn_mpls_demo" / "controller_policy.py"
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"

EXPECTED_CONTROLLER_TARGETS = {
    "access_hq_a",
    "access_hq_b",
    "access_hq_c",
    "access_backoffice",
    "access_hq_it",
    "voice_access",
    "core_hq",
    "access_telesale",
    "dist_telesale",
}


def load_engine() -> PolicyEngine:
    return PolicyEngine(POLICY_PATH)


def test_phase43_controller_target_set_dpids_and_runtime_alias_are_exact():
    model = load_network_model(MODEL_PATH)
    targets = set(controlled_switches(model))
    dpid_names = controller_dpid_name_map(model)
    runtime_names = runtime_switch_map(model)

    assert targets == EXPECTED_CONTROLLER_TARGETS
    assert len(targets) == 9
    assert set(dpid_names.values()) == EXPECTED_CONTROLLER_TARGETS
    assert len(dpid_names) == len(set(dpid_names)) == 9
    assert {
        logical: model["switches"][logical]["dpid"]
        for logical in targets
    } == {
        "access_hq_a": "0000000000000001",
        "access_hq_b": "0000000000000002",
        "access_hq_c": "0000000000000003",
        "voice_access": "0000000000000004",
        "core_hq": "0000000000000005",
        "access_telesale": "0000000000000006",
        "dist_telesale": "0000000000000007",
        "access_hq_it": "0000000000000008",
        "access_backoffice": "0000000000000009",
    }
    assert runtime_names["access_backoffice"] == "access_bo"
    assert runtime_switch_name(model, "access_backoffice") == "access_bo"
    assert set(runtime_names) == EXPECTED_CONTROLLER_TARGETS
    assert set(runtime_names.values()) == (EXPECTED_CONTROLLER_TARGETS - {"access_backoffice"}) | {"access_bo"}

    excluded = {
        "service_net",
        "ce_hq",
        "ce_telesale",
        "fw_hq",
        "fw_telesale",
        "mpls_cloud",
        "internet_zone",
        "h90",
        "hzalo",
        "hcall",
        "hsocial",
        "hinternet",
    }
    assert not targets.intersection(excluded)


def test_phase43_directional_telesale_backoffice_policy_uses_source_edge():
    engine = load_engine()

    telesale_to_backoffice = engine.decide("h50_01", "h60_01")
    backoffice_to_telesale = engine.decide("h60_01", "h50_01")

    assert telesale_to_backoffice == {
        "action": "deny",
        "reason": "Bi chan boi chinh sach cach ly VLAN 50 va VLAN 60.",
        "path": ["telesale", "access_telesale", "dist_telesale"],
        "blocked_at": "dist_telesale",
        "enforcement_point": "dist_telesale",
        "expected_reachable": False,
    }
    assert backoffice_to_telesale == {
        "action": "deny",
        "reason": "Bi chan boi chinh sach cach ly VLAN 50 va VLAN 60.",
        "path": ["backoffice", "access_backoffice", "core_hq"],
        "blocked_at": "core_hq",
        "enforcement_point": "core_hq",
        "expected_reachable": False,
    }


def test_phase43_project_isolation_remains_bidirectional_at_core_hq():
    engine = load_engine()
    endpoints = {"project_a": "h20_01", "project_b": "h30_01", "project_c": "h40_01"}

    for source_group, source in endpoints.items():
        for destination_group, destination in endpoints.items():
            if source_group == destination_group:
                continue
            decision = engine.decide(source, destination)
            assert decision["action"] == "deny"
            assert decision["blocked_at"] == "core_hq"
            assert decision["enforcement_point"] == "core_hq"
            assert decision["path"] == [
                source_group,
                engine.groups[source_group]["switch"],
                "core_hq",
            ]


def test_phase43_voice_and_internet_paths_match_approved_two_site_design():
    engine = load_engine()

    assert engine.decide("h60_01", "h90")["path"] == [
        "backoffice",
        "access_backoffice",
        "core_hq",
        "voice_access",
        "h90",
    ]
    assert engine.decide("h50_01", "h90")["path"] == [
        "telesale",
        "access_telesale",
        "dist_telesale",
        "ce_telesale",
        "mpls_cloud",
        "ce_hq",
        "core_hq",
        "voice_access",
        "h90",
    ]
    assert engine.decide("h60_01", "hzalo")["path"] == [
        "backoffice",
        "access_backoffice",
        "core_hq",
        "fw_hq",
        "internet_zone",
        "hzalo",
    ]
    assert engine.decide("h50_01", "hzalo")["path"] == [
        "telesale",
        "access_telesale",
        "dist_telesale",
        "fw_telesale",
        "internet_zone",
        "hzalo",
    ]


def test_phase43_isolation_flow_specs_have_exact_match_cookie_priority_and_placement():
    engine = load_engine()
    specs = engine.isolation_flow_specs()
    by_direction = {
        (spec["source_group"], spec["destination_group"]): spec
        for spec in specs
    }

    assert len(specs) == len(by_direction) == 8
    assert {spec["switch"] for spec in specs} == {"core_hq", "dist_telesale"}
    assert not {spec["switch"] for spec in specs}.intersection(
        EXPECTED_CONTROLLER_TARGETS - {"core_hq", "dist_telesale"}
    )

    telesale_drop = by_direction[("telesale", "backoffice")]
    assert telesale_drop == {
        "switch": "dist_telesale",
        "source_group": "telesale",
        "destination_group": "backoffice",
        "source_network": "172.16.50.0/24",
        "destination_network": "172.16.60.0/24",
        "match": {
            "eth_type": "ipv4",
            "ipv4_src": "172.16.50.0/24",
            "ipv4_dst": "172.16.60.0/24",
        },
        "action": "DROP",
        "policy": "telesale_backoffice_isolation",
        "cookie": 0x1002,
        "priority": 400,
    }
    backoffice_drop = by_direction[("backoffice", "telesale")]
    assert backoffice_drop["switch"] == "core_hq"
    assert backoffice_drop["source_network"] == "172.16.60.0/24"
    assert backoffice_drop["destination_network"] == "172.16.50.0/24"
    assert backoffice_drop["cookie"] == 0x1002
    assert backoffice_drop["priority"] == 400
    assert backoffice_drop["action"] == "DROP"

    project_drop = by_direction[("project_a", "project_b")]
    assert project_drop["switch"] == "core_hq"
    assert project_drop["cookie"] == 0x1001
    assert project_drop["priority"] == 400
    assert project_drop["match"] == {
        "eth_type": "ipv4",
        "ipv4_src": "172.16.20.0/24",
        "ipv4_dst": "172.16.30.0/24",
    }


def test_phase43_policy_reload_plan_is_stable_unique_and_cookie_reconciled():
    first = load_engine()
    second = load_engine()
    first_identities = first.isolation_flow_identities()
    second_identities = second.isolation_flow_identities()
    controller_source = CONTROLLER_PATH.read_text(encoding="utf-8")
    reload_body = controller_source.split("def reload_policy", 1)[1].split("def add_flow", 1)[0]

    assert first_identities == second_identities
    assert len(first_identities) == len(set(first_identities)) == 8
    assert "self._delete_cookie(datapath, cookie)" in reload_body
    assert reload_body.index("self._delete_cookie(datapath, cookie)") < reload_body.index(
        "self.install_policy_flows(datapath)"
    )
    assert "command=ofproto.OFPFC_DELETE" in controller_source
    assert "cookie_mask=0xFFFFFFFFFFFFFFFF" in controller_source
    assert "self._flow_record_identity(existing) != identity" in controller_source
    assert 'flow.get("cookie") == cookie_label' in controller_source
    assert '"action": "DELETE"' in controller_source
    assert POLICY_FLOW_PROFILES["telesale_backoffice_isolation"] == {
        "cookie": 0x1002,
        "priority": 400,
        "action": "DROP",
    }


def test_phase43_arp_transit_primes_first_allowed_path_without_bypassing_ipv4_policy():
    controller_source = CONTROLLER_PATH.read_text(encoding="utf-8")
    method_body = controller_source.split("def install_arp_transit_flow", 1)[1].split(
        "@set_ev_cls", 1
    )[0]
    switch_features_body = controller_source.split("def switch_features_handler", 1)[1].split(
        "@set_ev_cls", 1
    )[0]

    assert "parser.OFPMatch(eth_type=ether_types.ETH_TYPE_ARP)" in method_body
    assert "parser.OFPActionOutput(normal_port)" in method_body
    assert '"Baseline ARP transit; khong bypass policy IPv4."' in method_body
    assert "ipv4_src" not in method_body
    assert "ipv4_dst" not in method_body
    assert switch_features_body.index("self.install_arp_transit_flow(datapath)") < (
        switch_features_body.index("self.install_policy_flows(datapath)")
    )


def test_phase43_logical_api_id_and_runtime_ovs_bridge_contract():
    model = load_network_model(MODEL_PATH)
    topology_payload = live_mininet.topology_payload()
    logical_node_ids = {str(node["id"]) for node in topology_payload["nodes"]}
    topology_source = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert "access_backoffice" in logical_node_ids
    assert "access_bo" not in logical_node_ids
    assert "access_backoffice" in live_mininet.CONTROLLED_SWITCHES
    assert "access_bo" not in live_mininet.CONTROLLED_SWITCHES
    assert runtime_switch_name(model, "access_backoffice") == "access_bo"
    assert "return self.net.get(runtime_node_name(name))" in topology_source
    assert 'output = node.cmd(f"ovs-ofctl -O OpenFlow13 dump-flows {node.name}")' in topology_source
    assert '"runtime_ovs_bridges": {' in topology_source


def test_phase43_policy_keys_and_enforcement_are_free_of_retired_branch_assumptions():
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    controller_source = CONTROLLER_PATH.read_text(encoding="utf-8")
    active_sources = "\n".join((
        POLICY_PATH.read_text(encoding="utf-8"),
        controller_source,
        (REPO_ROOT / "sdn_mpls_demo" / "policy_engine.py").read_text(encoding="utf-8"),
    ))

    assert policy["policies"]["isolate_telesale_backoffice"] is True
    assert policy["policies"]["steer_telesale_internet_to"] == "fw_telesale"
    assert enforcement_switch_for_group(load_network_model(MODEL_PATH), "telesale") == "dist_telesale"
    assert enforcement_switch_for_group(load_network_model(MODEL_PATH), "backoffice") == "core_hq"
    for retired in (
        "access_branch",
        "dist_branch",
        "ce_branch",
        "fw_branch",
        '"Branch"',
        "'Branch'",
        "isolate_branch_vlan_50_60",
    ):
        assert retired not in active_sources
