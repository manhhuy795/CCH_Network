from __future__ import annotations

from scripts.network_model import (
    EXPECTED_CE_NODES,
    EXPECTED_CONTROLLED_SWITCHES,
    EXPECTED_FIREWALL_NODES,
    build_host_inventory,
    load_network_model,
    user_count,
    validate_network_model,
)
from sdn_mpls_demo.runtime_contract import source_truth_runtime_links


def test_full_sdn_collapsed_core_inventory_is_complete_and_valid():
    model = load_network_model()
    assert validate_network_model(model) == []
    assert set(model["switches"]) == EXPECTED_CONTROLLED_SWITCHES
    assert len(EXPECTED_CONTROLLED_SWITCHES) == 6
    assert EXPECTED_CE_NODES == {"ce_hq1", "ce_hq2", "ce_branch1", "ce_branch2"}
    assert {name for name, item in model["infrastructure"].items() if item.get("type") == "firewall"} == EXPECTED_FIREWALL_NODES
    assert user_count(model) == 90
    assert len(build_host_inventory(model)) == 111


def test_executable_builder_uses_enterprise_v7_entry_point():
    source = "sdn_mpls_demo/topology_enterprise_v7.py"
    text = open(source, encoding="utf-8").read()
    assert source_truth_runtime_links(load_network_model())
    assert "source_truth_runtime_links(NETWORK_MODEL)" in text
    assert "EnterpriseV7ControlAgent" in text
    assert "l2vpn_primary" in text
    assert "l2vpn_backup" in text
    assert "ipsec_l3" in text
    assert 'cryptographic_ipsec": False' in text
