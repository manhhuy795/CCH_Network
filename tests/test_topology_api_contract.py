from dashboard.backend.app.live_mininet import topology_payload


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
