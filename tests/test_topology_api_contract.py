from dashboard.backend.app.live_mininet import topology_payload
from dashboard.backend.app.topology import get_topology


def test_dashboard_topology_exposes_new_logical_inventory():
    payload = topology_payload()
    assert set(payload["logical_switches"][i]["logical_name"] for i in range(8)) == {
        "access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2",
        "core_hq", "access_branch", "dist_branch", "infra_access",
    }
    assert payload["summary"]["user_count"] == 110
    assert payload["summary"]["service_count"] == 5
    assert payload["summary"]["iot_hq_count"] == 5
    assert payload["summary"]["iot_branch_count"] == 2
    assert payload["summary"]["guest_count"] == 2
    assert {node["logical_name"] for node in payload["ce_nodes"]} == {"ce_hq", "ce_telesale"}
    assert {node["logical_name"] for node in payload["firewalls"]} == {"fw_hq", "fw_telesale"}


def test_dashboard_topology_keeps_controller_out_of_data_links():
    payload = topology_payload()
    for link in payload["links"]:
        assert "c0" not in {link["source"], link["target"]}
    assert payload["mpls"]["controller_managed"] is False


def test_dashboard_topology_exposes_source_truth_design_contract_without_runtime_fakes():
    payload = get_topology()
    contract = payload["topology_contract"]
    design_ids = {node["id"] for node in payload["design_nodes"]}
    runtime_ids = {node["logical_name"] for node in payload["devices"]}

    assert contract["source_of_truth"] == [
        "vars/network_model.yml",
        "vars/routing.yml",
        "vars/firewall_policies.yml",
    ]
    assert contract["design_only_is_runtime"] is False
    assert contract["provider_domain"]["circuits"]["primary"]["id"] == "isp_circuit_a"
    assert contract["provider_domain"]["circuits"]["backup"]["id"] == "isp_circuit_b"
    assert contract["provider_handoff_paths"]["primary"]["site_firewalls"]["hq"]["firewall"] == "fw_hq"
    assert contract["provider_handoff_paths"]["backup"]["site_firewalls"]["branch_telesale"]["firewall"] == "fw_telesale"
    assert contract["firewall_redundancy"]["hq"]["design_role"] == "ha_pair"
    assert contract["firewall_redundancy"]["hq"]["runtime_node"] == "fw_hq"
    assert contract["firewall_redundancy"]["branch_telesale"]["runtime_node"] == "fw_telesale"
    assert contract["server_zone"]["components"]["sbc_voice_edge"]["runtime_node"] == "h90"
    assert contract["server_zone"]["components"]["pbx_voice_inside"]["runtime_node"] == "h90"
    assert contract["server_zone"]["components"]["database_server"]["runtime_node"] is None
    assert design_ids.isdisjoint(runtime_ids)
    assert all(node["representation"] == "runtime" for node in payload["devices"])
    assert all(item["representation"] == "runtime" for item in payload["firewalls"])
    assert all(node["status"] == "design_only" for node in payload["design_nodes"])
    assert payload["summary"]["design_only_node_count"] == len(payload["design_nodes"])
    assert payload["summary"]["runtime_node_count"] == len(payload["devices"])
