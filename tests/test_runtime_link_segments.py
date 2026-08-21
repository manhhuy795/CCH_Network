from pathlib import Path

from scripts.network_model import endpoint_link_segments, load_network_model


ROOT = Path(__file__).resolve().parents[1]


def _endpoints(model, group: str, switch: str) -> set[str]:
    return {endpoint for endpoint, _switch in endpoint_link_segments(model, group, switch)}


def test_split_groups_only_map_endpoints_on_the_requested_access_switch():
    model = load_network_model()

    assert _endpoints(model, "project_b", "access_floor1") == {
        f"h30_{index:02d}" for index in range(1, 11)
    }
    assert _endpoints(model, "project_b", "access_floor2") == {
        f"h30_{index:02d}" for index in range(11, 21)
    }
    assert _endpoints(model, "project_c", "access_floor2") == {
        f"h40_{index:02d}" for index in range(1, 11)
    }
    assert _endpoints(model, "project_c", "access_branch") == {
        f"h40_{index:02d}" for index in range(11, 21)
    }


def test_explicit_iot_endpoint_names_are_preserved_in_runtime_segments():
    model = load_network_model()

    assert _endpoints(model, "iot_hq", "access_floor1") == {
        "iot_cam_01",
        "iot_cam_02",
        "ups_floor1",
        "ups_core_1",
        "ups_core_2",
    }
    assert _endpoints(model, "iot_branch", "access_branch") == {
        "iot_branch_cam_01",
        "ups_branch_1",
    }


def test_topology_control_agent_uses_inventory_based_link_segments():
    source = (ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py").read_text(encoding="utf-8")

    assert "endpoint_link_segments(NETWORK_MODEL, left, right)" in source
    assert "endpoint_link_segments(NETWORK_MODEL, right, left)" in source
