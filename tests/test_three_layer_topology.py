from __future__ import annotations

from scripts.network_model import (
    EXPECTED_CE_NODES,
    EXPECTED_CONTROLLED_SWITCHES,
    EXPECTED_FIREWALL_NODES,
    build_host_inventory,
    load_network_model,
    validate_network_model,
)


def test_three_layer_inventory_is_complete_and_valid():
    model = load_network_model()
    assert validate_network_model(model) == []
    assert set(model["switches"]) == EXPECTED_CONTROLLED_SWITCHES
    assert {name for name, item in model["infrastructure"].items() if item.get("type") == "router"} == EXPECTED_CE_NODES
    assert {name for name, item in model["infrastructure"].items() if item.get("type") == "firewall"} == EXPECTED_FIREWALL_NODES
    assert len(build_host_inventory(model)) == 133


def test_executable_builder_uses_redesigned_entry_point():
    source = ("sdn_mpls_demo/topology_hybrid_sdn.py")
    text = open(source, encoding="utf-8").read()
    active = text.rsplit("def build_topology():", 1)[-1]
    assert '"access_floor1"' in active
    assert '"dist_hq_1"' in active
    assert '"infra_access"' in active
    assert 'net.addHost("mpls_cloud"' not in active
