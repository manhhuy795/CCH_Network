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


# NHOM A: tat ca test Phase 41 ben duoi assert gia tri kien truc cu the.
def test_phase41_has_two_physical_sites_and_exact_inventory_counts():
    model = load_network_model()
    hosts = build_host_inventory(model)
    physical_sites = {name for name, data in model["sites"].items() if data["kind"] == "physical"}
    users = [host for host in hosts.values() if host["kind"] == "user"]
    services = [host for host in hosts.values() if host["kind"] == "service"]

    assert set(model["sites"]) == EXPECTED_SITES == {"hq", "branch_telesale", "wan", "internet"}
    assert physical_sites == EXPECTED_PHYSICAL_SITES == {"hq", "branch_telesale"}
    assert set(controlled_switches(model)) == EXPECTED_CONTROLLED_SWITCHES
    assert len(controlled_switches(model)) == 12
    assert {name for name, item in model["infrastructure"].items() if item["type"] == "router"} == EXPECTED_CE_NODES == {"ce_hq", "ce_telesale"}
    assert {name for name, item in model["infrastructure"].items() if item["type"] == "firewall"} == EXPECTED_FIREWALL_NODES == {"fw_hq", "fw_telesale"}
    assert model["host_groups"]["guest"]["vlan"] == 80
    assert model["host_groups"]["iot_ups"]["vlan"] == 110
    assert set(model["infrastructure_services"]) == {"hdhcp", "hdns", "hntp", "hmonitor"}
    assert len(users) == 110
    assert len(services) == 5


def test_phase41_backoffice_is_local_hq_and_uses_core_gateway():
    model = load_network_model()
    config = load_vars()
    group = model["host_groups"]["backoffice"]
    edges = {frozenset(link[:2]) for link in model["links"]}

    assert group["site"] == "hq"
    assert group["switch"] == "access_backoffice"
    assert group["gateway"] == "172.16.60.1"
    assert group["gateway_node"] == "core_hq"
    assert frozenset(("access_backoffice", "core_hq")) in edges
    assert config["sites"]["hq"]["kind"] == "physical"
    assert any(device["model_node"] == "access_backoffice" for device in config["sites"]["hq"]["devices"])
    assert next(vlan for vlan in config["vlans"] if vlan["id"] == 60)["site"] == "hq"
    assert 60 in next(device for device in config["sites"]["hq"]["devices"] if device["model_node"] == "core_hq")["svi_vlans"]


def test_phase41_reference_paths_match_voice_internet_and_mpls_design():
    paths = load_network_model()["reference_paths"]

    assert paths["hq_internet_hzalo"] == ["project_a", "access_hq_a", "core_hq", "fw_hq", "internet_zone", "hzalo"]
    assert paths["backoffice_internet_hzalo"] == ["backoffice", "access_backoffice", "core_hq", "fw_hq", "internet_zone", "hzalo"]
    assert "fw_telesale" not in paths["backoffice_internet_hzalo"]
    assert paths["backoffice_voice"] == ["backoffice", "access_backoffice", "core_hq", "voice_access", "h90"]
    assert not {"ce_hq", "ce_telesale", "mpls_cloud", "fw_hq", "fw_telesale"} & set(paths["backoffice_voice"])
    assert paths["telesale_voice"] == ["telesale", "access_telesale", "dist_telesale", "ce_telesale", "mpls_cloud", "ce_hq", "core_hq", "voice_access", "h90"]
    assert paths["telesale_internet_hzalo"] == ["telesale", "access_telesale", "dist_telesale", "fw_telesale", "internet_zone", "hzalo"]
    assert paths["backoffice_to_telesale"] == ["backoffice", "access_backoffice", "core_hq", "ce_hq", "mpls_cloud", "ce_telesale", "dist_telesale", "access_telesale", "telesale"]


def test_phase41_transit_links_are_eight_unique_private_slash30_networks():
    config = load_vars()
    links = config["links"]
    networks = [ipaddress.ip_network(link["cidr"]) for link in links.values()]
    endpoint_ips = [
        endpoint["ip"]
        for link in links.values()
        for endpoint in (link["endpoint_a"], link["endpoint_b"])
    ]

    assert set(links) == set(REQUIRED_TRANSIT_LINKS)
    assert len(networks) == len(set(networks)) == 8
    assert len(endpoint_ips) == len(set(endpoint_ips)) == 16
    assert all(network.prefixlen == 30 and network.is_private for network in networks)
    for index, left in enumerate(networks):
        assert all(not left.overlaps(right) for right in networks[index + 1:])


def test_phase41_firewall_ownership_uses_hq_for_backoffice():
    config = load_vars()
    firewall_sites = config["firewall_policy"]["sites"]

    assert set(firewall_sites) == {"hq", "branch_telesale"}
    assert firewall_sites["hq"]["firewall_name"] == "fw_hq"
    assert firewall_sites["hq"]["inside_node"] == "core_hq"
    assert set(firewall_sites["hq"]["owned_subnets"]) == {
        "172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24",
        "172.16.60.0/24", "172.16.70.0/24", "172.16.80.0/24", "172.16.110.0/24",
    }
    assert firewall_sites["hq"]["runtime_interfaces"] == {
        "inside": "fw_hq-eth0",
        "outside": "fw_hq-eth1",
    }
    assert config["firewall_policy"]["runtime_defaults"]["nat"]["enabled"] is False
    assert firewall_sites["branch_telesale"]["firewall_name"] == "fw_telesale"
    assert firewall_sites["branch_telesale"]["owned_subnets"] == ["172.16.50.0/24"]


def test_phase41_service_addressing_is_interface_plus_routed_vip():
    model = load_network_model()
    config = load_vars()
    service_routes = {
        route["service"]: (route["prefix"], route["next_hop"])
        for route in config["routes"]["internet_zone"]["service_routes"]
    }

    assert model["service_addressing"]["model"] == "interface_plus_service_vip"
    assert model["service_addressing"]["interface_subnet"] == "10.255.30.0/24"
    assert model["service_addressing"]["gateway_ip"] == "10.255.30.1"
    assert config["service_zone"]["addressing_model"] == "interface_plus_service_vip"
    for name in ("hzalo", "hcall", "hsocial", "hinternet"):
        service = model["services"][name]
        assert ipaddress.ip_network(service["subnet"]).prefixlen == 32
        assert ipaddress.ip_interface(service["interface_cidr"]).network == ipaddress.ip_network("10.255.30.0/24")
        assert service["interface_ip"] == service["transit_ip"]
        assert service["gateway"] == "10.255.30.1"
        assert service_routes[name] == (service["subnet"], service["interface_ip"])


def test_phase41_has_no_active_remote_backoffice_nodes_or_routes():
    model = load_network_model()
    config = load_vars()
    forbidden = {"branch_backoffice", "dist_backoffice", "ce_backoffice", "fw_backoffice"}
    active_nodes = set(model["host_groups"]) | set(model["services"]) | set(model["switches"]) | set(model["infrastructure"])

    assert not active_nodes & forbidden
    assert not set(config["sites"]) & forbidden
    assert not set(config["routes"]) & forbidden
    assert not set(config["firewall_policy"]["sites"]) & forbidden
    assert validate_network_model(model) == []
    assert validate_all(config) == []


def test_phase41_validation_rejects_duplicate_nodes_dpids_and_retired_nodes():
    model = load_network_model()

    duplicate_node = deepcopy(model)
    duplicate_node["services"]["access_hq_a"] = deepcopy(duplicate_node["services"]["hzalo"])
    assert any("Duplicate topology node IDs" in error for error in validate_network_model(duplicate_node))

    duplicate_dpid = deepcopy(model)
    duplicate_dpid["switches"]["access_backoffice"]["dpid"] = duplicate_dpid["switches"]["core_hq"]["dpid"]
    assert any("Duplicate switch DPIDs" in error for error in validate_network_model(duplicate_dpid))

    retired_node = deepcopy(model)
    retired_node["infrastructure"]["fw_backoffice"] = {"label": "retired", "type": "firewall", "site": "hq"}
    assert any("Legacy or retired topology nodes" in error for error in validate_network_model(retired_node))


def test_phase41_validation_rejects_overlap_and_missing_firewall_outside_link():
    overlap = deepcopy(load_vars())
    overlap["links"]["fw_telesale_to_internet_zone"]["cidr"] = overlap["links"]["fw_hq_to_internet_zone"]["cidr"]
    assert any("overlap" in error.lower() for error in validate_all(overlap))

    missing_outside = deepcopy(load_vars())
    del missing_outside["links"]["fw_telesale_to_internet_zone"]
    errors = validate_all(missing_outside)
    assert any("Transit links must be exactly" in error for error in errors)
    assert any("fw_telesale must have one firewall_inside and one firewall_outside" in error for error in errors)


def test_phase41_migration_note_is_not_an_active_topology_definition():
    model = load_network_model()
    note = model["metadata"]["migration_note"]

    for retired_name in ("access_branch", "dist_branch", "ce_branch", "fw_branch", "branch_backoffice", "dist_backoffice", "ce_backoffice", "fw_backoffice"):
        assert retired_name in note
    assert "active topology node" in note
