from copy import deepcopy

from scripts.common import load_vars
from scripts.validate_vars import validate_all


# NHOM A: routing tests assert prefix, next-hop va ownership cu the.
def test_two_ce_mpls_routes_point_to_their_direct_mpls_peer_only():
    config = load_vars()
    expected_peers = {"ce_hq": "10.255.0.2", "ce_telesale": "10.255.0.6"}

    assert set(config["ce_router_ips"]) == set(expected_peers) == {"ce_hq", "ce_telesale"}
    for ce_name, expected_peer in expected_peers.items():
        assert config["routes"][ce_name]["provider_next_hop"] == expected_peer
        assert {route["next_hop"] for route in config["routes"][ce_name]["mpls_routes"]} == {expected_peer}


def test_two_physical_sites_have_independent_local_internet_breakout():
    config = load_vars()

    assert config["routes"]["core_hq"]["default_route"]["next_hop"] == "10.10.254.2"
    assert config["routes"]["dist_telesale"]["default_route"]["next_hop"] == "10.20.254.2"
    assert config["routes"]["fw_hq"]["default_route"]["next_hop"] == "10.255.10.2"
    assert config["routes"]["fw_telesale"]["default_route"]["next_hop"] == "10.255.10.6"
    assert "dist_backoffice" not in config["routes"]
    assert "fw_backoffice" not in config["routes"]


def test_vlan60_is_local_to_hq_and_remote_from_telesale():
    routes = load_vars()["routes"]

    assert all(route["prefix"] != "172.16.60.0/24" for route in routes["core_hq"]["intersite_routes"])
    assert {route["prefix"] for route in routes["ce_hq"]["internal_routes"]} >= {"172.16.60.0/24"}
    assert {route["prefix"] for route in routes["ce_hq"]["mpls_routes"]} == {"172.16.50.0/24"}
    assert {route["prefix"] for route in routes["ce_telesale"]["mpls_routes"]} >= {"172.16.60.0/24"}
    assert {route["prefix"] for route in routes["fw_hq"]["internal_routes"]} >= {"172.16.60.0/24"}
    vlan60_return = next(route for route in routes["internet_zone"]["internal_routes"] if route["prefix"] == "172.16.60.0/24")
    assert vlan60_return["next_hop"] == "10.255.10.1"


def test_validation_rejects_direct_ce_to_remote_ce_next_hop():
    config = deepcopy(load_vars())
    config["routes"]["ce_hq"]["mpls_routes"][0]["next_hop"] = config["ce_router_ips"]["ce_telesale"]["wan_ip"]

    errors = validate_all(config)

    assert any("remote CE" in error for error in errors)
    assert any("not directly adjacent" in error for error in errors)
