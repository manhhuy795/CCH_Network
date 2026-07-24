from copy import deepcopy

from scripts.common import load_vars
from scripts.validate_vars import validate_all


def test_two_ce_mpls_routes_use_direct_provider_handoffs_and_metrics():
    routes = load_vars()["routes"]
    assert routes["ce_hq"]["primary"] == {"next_hop": "10.255.0.2", "metric": 10}
    assert routes["ce_hq"]["backup"] == {"next_hop": "10.255.0.10", "metric": 100}
    assert routes["ce_telesale"]["primary"] == {"next_hop": "10.255.0.5", "metric": 10}
    assert routes["ce_telesale"]["backup"] == {"next_hop": "10.255.0.13", "metric": 100}
    assert routes["mpls_primary"]["routes"][1]["next_hop"] == "10.255.0.6"
    assert routes["mpls_backup"]["routes"][1]["next_hop"] == "10.255.0.14"


def test_two_physical_sites_have_independent_local_internet_breakout():
    routes = load_vars()["routes"]
    assert routes["hq_l3_gateway"]["default_route"]["next_hop"] == "10.10.254.2"
    assert routes["telesale_l3_gateway"]["default_route"]["next_hop"] == "10.20.254.2"
    config = load_vars()
    assert config["fw_hq"]["default_route"]["next_hop"] == "10.255.10.2"
    assert config["fw_telesale"]["default_route"]["next_hop"] == "10.255.10.6"
    assert "dist_backoffice" not in routes
    assert "fw_backoffice" not in routes


def test_vlan60_is_local_to_hq_and_remote_from_telesale():
    routes = load_vars()["routes"]
    assert {route["prefix"] for route in routes["ce_hq"]["internal_routes"]} == {"172.16.0.0/16"}
    assert {route["prefix"] for route in load_vars()["ce_telesale"]["mpls_routes"]} == {"172.16.0.0/16"}
    assert {route["prefix"] for route in routes["telesale_l3_gateway"]["user_routes"]} >= {"172.16.60.0/24"}


def test_validate_all_rejects_transit_overlap():
    config = deepcopy(load_vars())
    config["links"]["fw_telesale_to_internet_zone"]["cidr"] = config["links"]["fw_hq_to_internet_zone"]["cidr"]
    assert any("overlap" in error.lower() for error in validate_all(config))
