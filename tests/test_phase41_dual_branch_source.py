from copy import deepcopy
import ipaddress
from pathlib import Path

from scripts.common import load_vars
from scripts.network_model import (
    EXPECTED_CE_NODES,
    EXPECTED_CONTROLLED_SWITCHES,
    EXPECTED_FIREWALL_NODES,
    EXPECTED_SITES,
    build_host_inventory,
    controlled_switches,
    load_network_model,
    validate_network_model,
)
from scripts.validate_vars import REQUIRED_TRANSIT_LINKS, validate_all


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_phase41_dual_branch_source_of_truth_counts_and_ownership():
    model = load_network_model()
    hosts = build_host_inventory(model)
    users = [host for host in hosts.values() if host["kind"] == "user"]
    services = [host for host in hosts.values() if host["kind"] == "service"]

    assert set(model["sites"]) == EXPECTED_SITES
    assert model["host_groups"]["telesale"]["site"] == "branch_telesale"
    assert model["host_groups"]["telesale"]["switch"] == "access_telesale"
    assert model["host_groups"]["backoffice"]["site"] == "branch_backoffice"
    assert model["host_groups"]["backoffice"]["switch"] == "access_backoffice"
    assert set(controlled_switches(model)) == EXPECTED_CONTROLLED_SWITCHES
    assert len(controlled_switches(model)) == 10
    assert {name for name, item in model["infrastructure"].items() if item["type"] == "router"} == EXPECTED_CE_NODES
    assert {name for name, item in model["infrastructure"].items() if item["type"] == "firewall"} == EXPECTED_FIREWALL_NODES
    assert len(users) == 110
    assert len(services) == 5
    assert validate_network_model(model) == []


def test_phase41_transit_links_are_unique_valid_and_non_overlapping():
    config = load_vars()
    links = config["links"]
    assert set(links) == set(REQUIRED_TRANSIT_LINKS)
    assert config["transit_addressing"]["prefix_length"] == 30
    assert config["transit_addressing"]["rationale"]

    networks = [ipaddress.ip_network(link["cidr"]) for link in links.values()]
    endpoint_ips = [
        endpoint["ip"]
        for link in links.values()
        for endpoint in (link["endpoint_a"], link["endpoint_b"])
    ]
    assert all(network.prefixlen == 30 for network in networks)
    assert len(networks) == len(set(networks)) == 12
    assert len(endpoint_ips) == len(set(endpoint_ips)) == 24
    for index, left in enumerate(networks):
        assert all(not left.overlaps(right) for right in networks[index + 1:])
    assert validate_all(config) == []


def test_phase41_sites_firewalls_and_routes_have_no_shared_branch_nodes():
    config = load_vars()
    model = load_network_model()
    forbidden = {"access_branch", "dist_branch", "ce_branch", "fw_branch"}
    topology_nodes = (
        set(model["host_groups"])
        | set(model["services"])
        | set(model["switches"])
        | set(model["infrastructure"])
    )
    assert not topology_nodes & forbidden
    assert not set(config["routes"]) & forbidden

    expected_branch_nodes = {
        "branch_telesale": {"access_telesale", "dist_telesale", "ce_telesale", "fw_telesale"},
        "branch_backoffice": {"access_backoffice", "dist_backoffice", "ce_backoffice", "fw_backoffice"},
    }
    for site, expected_nodes in expected_branch_nodes.items():
        actual_nodes = {device["model_node"] for device in config["sites"][site]["devices"]}
        assert actual_nodes == expected_nodes

    firewall_sites = config["firewall_policy"]["sites"]
    assert firewall_sites["hq"]["firewall_name"] == "fw_hq"
    assert firewall_sites["branch_telesale"]["firewall_name"] == "fw_telesale"
    assert firewall_sites["branch_telesale"]["owned_subnets"] == ["172.16.50.0/24"]
    assert firewall_sites["branch_backoffice"]["firewall_name"] == "fw_backoffice"
    assert firewall_sites["branch_backoffice"]["owned_subnets"] == ["172.16.60.0/24"]


def test_phase41_validation_rejects_duplicate_nodes_dpids_and_legacy_nodes():
    model = load_network_model()

    duplicate_node = deepcopy(model)
    duplicate_node["services"]["access_hq_a"] = deepcopy(duplicate_node["services"]["hzalo"])
    assert any("Duplicate topology node IDs" in error for error in validate_network_model(duplicate_node))

    duplicate_dpid = deepcopy(model)
    duplicate_dpid["switches"]["dist_backoffice"]["dpid"] = duplicate_dpid["switches"]["core_hq"]["dpid"]
    assert any("Duplicate switch DPIDs" in error for error in validate_network_model(duplicate_dpid))

    legacy_node = deepcopy(model)
    legacy_node["infrastructure"]["fw_branch"] = {"label": "legacy", "type": "firewall", "site": "branch_telesale"}
    assert any("Legacy shared Branch nodes" in error for error in validate_network_model(legacy_node))


def test_phase41_validation_rejects_overlap_and_missing_firewall_outside_link():
    overlap = deepcopy(load_vars())
    overlap["links"]["fw_backoffice_to_internet_zone"]["cidr"] = overlap["links"]["fw_telesale_to_internet_zone"]["cidr"]
    assert any("overlap" in error.lower() for error in validate_all(overlap))

    missing_outside = deepcopy(load_vars())
    del missing_outside["links"]["fw_backoffice_to_internet_zone"]
    errors = validate_all(missing_outside)
    assert any("Transit links must be exactly" in error for error in errors)
    assert any("fw_backoffice must have one firewall_inside and one firewall_outside" in error for error in errors)


def test_phase41_only_documents_legacy_names_as_a_migration_guard():
    model = load_network_model()
    note = model["metadata"]["migration_note"]
    for legacy_name in ("access_branch", "dist_branch", "ce_branch", "fw_branch"):
        assert legacy_name in note
    assert "Phase 46" in note
