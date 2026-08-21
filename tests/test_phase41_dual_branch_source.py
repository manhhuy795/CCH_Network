from copy import deepcopy
import ipaddress

from scripts.common import load_vars
from scripts.network_model import (
    EXPECTED_CE_NODES,
    EXPECTED_CONTROLLED_SWITCHES,
    EXPECTED_FIREWALL_NODES,
    EXPECTED_PHYSICAL_SITES,
    EXPECTED_SITES,
    build_host_inventory,
    controlled_switches,
    load_network_model,
    validate_network_model,
)
from scripts.validate_vars import REQUIRED_TRANSIT_LINKS, validate_all


def test_phase41_has_two_physical_sites_and_exact_inventory_counts():
    model = load_network_model()
    hosts = build_host_inventory(model)
    physical_sites = {name for name, data in model["sites"].items() if data["kind"] == "physical"}
    users = [host for host in hosts.values() if host["kind"] == "user"]
    services = [host for host in hosts.values() if host["kind"] == "service"]

    assert set(model["sites"]) == EXPECTED_SITES == {"hq", "branch_telesale", "wan", "internet"}
    assert physical_sites == EXPECTED_PHYSICAL_SITES == {"hq", "branch_telesale"}
    assert set(controlled_switches(model)) == EXPECTED_CONTROLLED_SWITCHES
    assert len(controlled_switches(model)) == 8
    assert {name for name, item in model["infrastructure"].items() if item["type"] == "router"} == EXPECTED_CE_NODES
    assert {name for name, item in model["infrastructure"].items() if item["type"] == "firewall"} == EXPECTED_FIREWALL_NODES
    assert model["host_groups"]["guest"]["vlan"] == 120
    assert model["host_groups"]["iot_hq"]["vlan"] == 110
    assert model["host_groups"]["iot_branch"]["vlan"] == 111
    assert set(model["infrastructure_services"]) == {"hdhcp", "hdns", "hntp", "hmonitor", "hnvr", "hrecording", "hdialer", "hbackup", "had"}
    assert len(users) == 110
    assert len(services) == 5


def test_phase41_floor_and_branch_placement_is_authoritative():
    model = load_network_model()
    config = load_vars()
    edges = {frozenset(link[:2]) for link in model["links"]}

    assert model["host_groups"]["backoffice"]["site"] == "hq"
    assert model["host_groups"]["backoffice"]["floor"] == "floor2"
    assert model["host_groups"]["backoffice"]["switch"] == "access_floor2"
    assert model["host_groups"]["project_b"]["placements"] == [
        {"floor": "floor1", "switch": "access_floor1", "count": 10},
        {"floor": "floor2", "switch": "access_floor2", "count": 10},
    ]
    assert frozenset(("access_floor2", "dist_hq_2")) in edges
    assert not any(device["model_node"] == "branch_backoffice" for site in config["sites"].values() for device in site.get("devices", []))
    assert not any(device["model_node"] == "access_backoffice" for device in config["sites"]["branch_telesale"]["devices"])


def test_phase41_reference_paths_match_enterprise_dataflows():
    paths = load_network_model()["reference_paths"]

    assert paths["project_a_internet"] == ["project_a", "access_floor1", "dist_hq_1", "core_hq", "fw_hq", "internet_zone", "hzalo"]
    assert paths["project_b_floor2"] == ["project_b", "access_floor2", "dist_hq_2", "core_hq"]
    assert paths["backoffice_voice"] == ["backoffice", "access_floor2", "dist_hq_2", "core_hq", "infra_access", "h90"]
    assert paths["telesale_voice_primary"] == ["telesale", "access_branch", "dist_branch", "ce_telesale", "mpls_primary", "ce_hq", "core_hq", "infra_access", "h90"]
    assert paths["iot_branch_monitoring"][-3:] == ["core_hq", "infra_access", "hmonitor"]
    assert "fw_hq" not in paths["telesale_voice_primary"]
    assert "fw_telesale" not in paths["iot_branch_monitoring"]


def test_phase41_transit_links_are_unique_private_slash30_networks():
    links = load_vars()["links"]
    networks = [ipaddress.ip_network(link["cidr"]) for link in links.values()]
    endpoint_ips = [endpoint["ip"] for link in links.values() for endpoint in (link["endpoint_a"], link["endpoint_b"])]

    assert set(links) == set(REQUIRED_TRANSIT_LINKS)
    assert len(networks) == len(set(networks)) == 10
    assert len(endpoint_ips) == len(set(endpoint_ips)) == 20
    assert all(network.prefixlen == 30 and network.is_private for network in networks)
    for index, left in enumerate(networks):
        assert all(not left.overlaps(right) for right in networks[index + 1:])


def test_phase41_firewall_ownership_and_no_nat():
    config = load_vars()
    firewall_sites = config["firewall_policy"]["sites"]

    assert firewall_sites["hq"]["firewall_name"] == "fw_hq"
    assert firewall_sites["hq"]["inside_node"] == "core_hq"
    assert set(firewall_sites["hq"]["owned_subnets"]) == {
        "172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.60.0/24",
        "172.16.70.0/24", "172.16.90.0/24", "172.16.100.0/24", "172.16.110.0/24", "172.16.120.0/24",
    }
    assert firewall_sites["branch_telesale"]["inside_node"] == "dist_branch"
    assert set(firewall_sites["branch_telesale"]["owned_subnets"]) == {"172.16.50.0/24", "172.16.111.0/24"}
    assert config["firewall_policy"]["runtime_defaults"]["nat"]["enabled"] is False


def test_phase41_service_addressing_is_interface_plus_routed_vip():
    model = load_network_model()
    config = load_vars()

    assert model["service_addressing"]["model"] == "interface_plus_service_vip"
    assert model["service_addressing"]["gateway_ip"] == "10.255.30.1"
    assert config["service_zone"]["addressing_model"] == "interface_plus_service_vip"
    for name in ("hzalo", "hcall", "hsocial", "hinternet"):
        service = model["services"][name]
        assert ipaddress.ip_network(service["subnet"]).prefixlen == 32
        assert ipaddress.ip_interface(service["interface_cidr"]).network == ipaddress.ip_network("10.255.30.0/24")
        assert service["interface_ip"] == service["transit_ip"]


def test_phase41_has_no_active_retired_branch_nodes():
    model = load_network_model()
    config = load_vars()
    forbidden = {"branch_backoffice", "dist_backoffice", "ce_backoffice", "fw_backoffice", "ce_branch", "fw_branch"}
    active_nodes = set(model["host_groups"]) | set(model["services"]) | set(model["switches"]) | set(model["infrastructure"])

    assert not active_nodes & forbidden
    assert not set(config["firewall_policy"]["sites"]) & forbidden
    assert validate_network_model(model) == []
    assert validate_all(config) == []


def test_phase41_validation_rejects_duplicate_nodes_dpids_and_retired_nodes():
    model = load_network_model()

    duplicate_node = deepcopy(model)
    duplicate_node["services"]["core_hq"] = deepcopy(duplicate_node["services"]["hzalo"])
    assert any("Duplicate topology node IDs" in error for error in validate_network_model(duplicate_node))

    duplicate_dpid = deepcopy(model)
    duplicate_dpid["switches"]["access_floor2"]["dpid"] = duplicate_dpid["switches"]["core_hq"]["dpid"]
    assert any("Duplicate switch DPIDs" in error for error in validate_network_model(duplicate_dpid))

    retired_node = deepcopy(model)
    retired_node["infrastructure"]["fw_backoffice"] = {"label": "retired", "type": "firewall", "site": "hq"}
    assert any("Legacy or retired topology nodes" in error for error in validate_network_model(retired_node))


def test_phase41_validation_rejects_transit_overlap_and_missing_firewall_link():
    overlap = deepcopy(load_vars())
    overlap["links"]["fw_telesale_to_internet_zone"]["cidr"] = overlap["links"]["fw_hq_to_internet_zone"]["cidr"]
    assert any("overlap" in error.lower() for error in validate_all(overlap))

    missing_outside = deepcopy(load_vars())
    del missing_outside["links"]["fw_telesale_to_internet_zone"]
    errors = validate_all(missing_outside)
    assert any("Transit links must be exactly" in error for error in errors)
    assert any("fw_telesale must have one firewall_inside and one firewall_outside" in error for error in errors)


def test_phase41_migration_note_identifies_only_retired_names():
    note = load_network_model()["metadata"]["migration_note"]
    for retired_name in ("access_hq_a", "access_hq_b", "access_hq_c", "voice_access", "branch_backoffice", "fw_backoffice"):
        assert retired_name in note
