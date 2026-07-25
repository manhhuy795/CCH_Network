import re
from pathlib import Path

import yaml

from scripts.network_model import build_host_inventory, controlled_switches, load_network_model, validate_network_model
from sdn_mpls_demo.policy_engine import POLICY_FLOW_PROFILES, PolicyEngine
from sdn_mpls_demo.runtime_contract import RUNTIME_BACKBONE_LINK_MAP, source_truth_runtime_links


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "vars" / "network_model.yml"
POLICY_PATH = ROOT / "sdn_mpls_demo" / "policy.yml"
TOPOLOGY_PATH = ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"
CONTROLLER_PATH = ROOT / "sdn_mpls_demo" / "controller_policy.py"


def test_network_model_is_single_source_of_truth():
    model = load_network_model(MODEL_PATH)
    hosts = build_host_inventory(model)
    assert sum(host["kind"] == "user" for host in hosts.values()) == 110
    assert sum(host["kind"] == "service" for host in hosts.values()) == 5
    assert len(hosts) == 133
    assert len(set(host["ip"] for host in hosts.values())) == len(hosts)
    assert set(controlled_switches(model)) == {
        "access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2", "core_hq", "access_branch", "dist_branch", "infra_access"
    }
    assert model["services"]["h90"]["switch"] == "infra_access"
    assert model["host_groups"]["backoffice"]["site"] == "hq"
    assert model["host_groups"]["backoffice"]["floor"] == "floor2"
    assert validate_network_model(model) == []


def test_network_model_validation_catches_inventory_drift():
    model = load_network_model(MODEL_PATH)
    model["host_groups"]["it_support"]["count"] = 4
    errors = validate_network_model(model)
    assert any("110 user hosts" in error for error in errors)
    assert any("133 endpoints" in error for error in errors)


def test_topology_uses_three_layers_two_mpls_clouds_and_no_old_shared_nodes():
    source = TOPOLOGY_PATH.read_text(encoding="utf-8")
    model = load_network_model(MODEL_PATH)
    assert set(RUNTIME_BACKBONE_LINK_MAP) == {
        frozenset((source_name, target_name))
        for source_name, target_name, _kind in model["links"]
        if {source_name, target_name}.issubset(set(model["switches"]) | set(model["infrastructure"]))
    }
    assert source_truth_runtime_links(model)
    assert "runtime_nodes = {" in source
    assert "source_truth_runtime_links(NETWORK_MODEL)" in source
    assert 'net.addHost("mpls_cloud"' not in source.split("def build_topology():")[-1]
    explicit_interfaces = re.findall(r'intfName[12]="([^"\\]+)"', source.split("def build_topology():")[-1])
    assert explicit_interfaces
    assert all(len(name) <= 15 for name in explicit_interfaces)
    assert len(explicit_interfaces) == len(set(explicit_interfaces))


def test_l3_gateway_owns_all_declared_vlan_gateways_and_branch_iot():
    source = TOPOLOGY_PATH.read_text(encoding="utf-8")
    for vlan in (20, 30, 40, 60, 70, 90, 100, 110, 111, 120):
        assert f'172.16.{vlan}.1/24' in source
    assert '"ce_telesale_to_dist_branch"' in source
    assert '"mpls_primary_to_ce_telesale"' in source
    assert '"mpls_backup_to_ce_telesale"' in source


def test_only_eight_ovs_are_controller_managed_and_service_bridge_is_not_model_ovs():
    model = load_network_model(MODEL_PATH)
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")
    assert len(controlled_switches(model)) == 8
    assert 'service_net.start([])' in topology
    assert 'service_net.start([controller])' not in topology
    assert 'SERVICE_NET_MININET_DPID = "00000000000000fe"' in topology


def test_firewall_and_mpls_nodes_are_not_openflow_devices():
    model = load_network_model(MODEL_PATH)
    controller_targets = set(controlled_switches(model))
    assert not controller_targets.intersection({"fw_hq", "fw_telesale", "ce_hq", "ce_telesale", "mpls_primary", "mpls_backup"})
    assert model["infrastructure"]["fw_hq"]["label"] == "Firewall HQ Internet Edge"
    assert model["infrastructure"]["fw_telesale"]["label"] == "Firewall Branch Internet Edge"


def test_new_diagram_edge_design_is_logical_and_maps_both_provider_circuits():
    model = load_network_model(MODEL_PATH)
    edge = model["edge_design"]
    assert edge["provider_domain"]["mode"] == "logical_provider_demarcation"
    assert edge["provider_domain"]["circuits"]["primary"]["id"] == "isp_circuit_a"
    assert edge["provider_domain"]["circuits"]["backup"]["id"] == "isp_circuit_b"
    assert edge["firewalls"]["hq"]["design_role"] == "ha_pair"
    assert edge["firewalls"]["hq"]["outside_circuits"] == ["primary", "backup"]
    assert edge["firewalls"]["branch_telesale"]["runtime_node"] == "fw_telesale"
    assert validate_network_model(model) == []


def test_server_zone_design_does_not_fake_sbc_pbx_or_database_runtime_nodes():
    model = load_network_model(MODEL_PATH)
    components = model["server_zone_design"]["components"]
    assert components["sbc_voice_edge"]["runtime_node"] == "h90"
    assert components["pbx_voice_inside"]["runtime_node"] == "h90"
    assert components["database_server"]["runtime_node"] is None
    assert validate_network_model(model) == []


def test_design_only_source_truth_annotations_are_explicit():
    model = load_network_model(MODEL_PATH)
    circuits = model["edge_design"]["provider_domain"]["circuits"]
    assert all(item["representation"] == "design_only" for item in circuits.values())
    assert all(item["runtime_node"] is None for item in circuits.values())
    assert all(item["controller_managed"] is False for item in circuits.values())
    components = model["server_zone_design"]["components"]
    assert components["database_server"]["representation"] == "design_only"
    assert components["database_server"]["runtime_node"] is None
    assert all(item["representation"] == "design_metadata" for name, item in components.items() if name != "database_server")


def test_network_model_validation_rejects_design_only_runtime_node_and_invalid_link_type():
    model = load_network_model(MODEL_PATH)
    model["edge_design"]["provider_domain"]["circuits"]["primary"]["runtime_node"] = "core_hq"
    model["links"].append(["core_hq", "ce_hq", "unknown"])
    errors = validate_network_model(model)
    assert any("Provider circuit primary must be explicitly design-only" in error for error in errors)
    assert any("invalid type 'unknown'" in error for error in errors)


def test_controller_is_real_openflow_13_and_drops_are_at_core_or_branch_distribution():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    engine = PolicyEngine(POLICY_PATH)
    assert "app_manager.OSKenApp" in controller
    assert "ofproto_v1_3.OFP_VERSION" in controller
    assert "OFPFlowMod" in controller
    assert {spec["switch"] for spec in engine.isolation_flow_specs()} == {"core_hq", "dist_branch"}
    assert all(spec["action"] == "DROP" for spec in engine.isolation_flow_specs())
    assert POLICY_FLOW_PROFILES["hq_project_isolation"]["priority"] == 400
    assert 'Khong cai isolation DROP tren %s; access OVS chi transit/local switching.' in controller


def test_runtime_policy_matrix_and_controller_lifecycle_remain_present():
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    assert "POLICY_TESTS = (" in topology
    assert '"LINK_DOWN"' in topology
    assert '"LINK_UP"' in topology
    assert "reload_policy" in controller
    assert "cookie_mask=0xFFFFFFFFFFFFFFFF" in controller
