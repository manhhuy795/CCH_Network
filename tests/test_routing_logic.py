from copy import deepcopy

from scripts.common import load_vars
from scripts.validate_vars import validate_all


def test_ce_mpls_routes_point_to_isp_pe_only():
    config = load_vars()

    assert {route["next_hop"] for route in config["routes"]["hq-ce-router"]["mpls_routes"]} == {
        config["links"]["hq"]["ce_to_pe"]["pe_ip"]
    }
    assert {route["next_hop"] for route in config["routes"]["br-ce-router"]["mpls_routes"]} == {
        config["links"]["branch"]["ce_to_pe"]["pe_ip"]
    }


def test_validation_rejects_direct_ce_to_ce_next_hop():
    config = deepcopy(load_vars())
    config["routes"]["hq-ce-router"]["mpls_routes"][0]["next_hop"] = config["ce_router_ips"][
        "br-ce-router"
    ]["wan_ip"]

    errors = validate_all(config)

    assert any("remote CE" in error for error in errors)
