from __future__ import annotations

from scripts.network_model import load_network_model
from sdn_mpls_demo.runtime_contract import (
    RUNTIME_BACKBONE_LINK_MAP,
    RUNTIME_COLLAPSED_GATEWAYS,
    source_truth_runtime_links,
)


def test_runtime_backbone_mapping_covers_every_declared_infrastructure_link():
    model = load_network_model()
    infrastructure = set(model["infrastructure"]) | set(model["switches"])
    declared = {
        frozenset((source, target))
        for source, target, _kind in model["links"]
        if {source, target}.issubset(infrastructure)
    }

    assert declared == set(RUNTIME_BACKBONE_LINK_MAP)
    runtime_links = source_truth_runtime_links(model)
    assert runtime_links
    assert all(len(left) <= 15 and len(right) <= 15 for _, _, left, right, _, _ in runtime_links)


def test_collapsed_l3_gateways_are_runtime_implementation_details_only():
    model = load_network_model()
    runtime_links = source_truth_runtime_links(model)
    runtime_nodes = {node for left, right, *_rest in runtime_links for node in (left, right)}

    assert RUNTIME_COLLAPSED_GATEWAYS == {
        "core_hq": "hq_l3_gateway",
        "dist_branch": "telesale_l3_gateway",
    }
    assert set(RUNTIME_COLLAPSED_GATEWAYS.values()).issubset(runtime_nodes)
    assert set(RUNTIME_COLLAPSED_GATEWAYS.values()).isdisjoint(model["infrastructure"])
    assert {"isp_circuit_a", "isp_circuit_b", "wan_handoff_primary", "wan_handoff_backup"}.isdisjoint(runtime_nodes)


def test_runtime_backbone_has_no_duplicate_interface_endpoint():
    runtime_links = source_truth_runtime_links()
    endpoints = [(left, intf_left) for left, _right, intf_left, _intf_right, _bw, _delay in runtime_links]
    endpoints.extend((right, intf_right) for _left, right, _intf_left, intf_right, _bw, _delay in runtime_links)

    assert len(endpoints) == len(set(endpoints))
