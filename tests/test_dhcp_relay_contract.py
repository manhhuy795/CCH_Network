from scripts.network_model import load_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine


def test_dhcp_is_centralized_and_relayed_at_l3():
    model = load_network_model()
    policy = PolicyEngine(__import__("pathlib").Path("sdn_mpls_demo/policy.yml")).policy_data
    assert policy["dhcp"]["server"] == "hdhcp"
    assert policy["dhcp"]["relay_gateways"] == ["core_hq", "dist_branch"]
    assert model["infrastructure_services"]["hdhcp"]["ip"] == "172.16.100.10"
    assert model["infrastructure_services"]["hdhcp"]["switch"] == "infra_access"
    for scope in policy["dhcp"]["scopes"].values():
        assert scope["dns"] == "172.16.100.11"
        assert scope["gateway"].endswith(".1")


def test_guest_and_iot_can_reach_only_declared_bootstrap_services():
    engine = PolicyEngine(__import__("pathlib").Path("sdn_mpls_demo/policy.yml"))
    assert engine.decide("guest_01", "hdhcp")["action"] == "allow"
    assert engine.decide("guest_01", "hdns")["action"] == "allow"
    assert engine.decide("guest_01", "h20_01")["action"] == "deny"
    assert engine.decide("iot_cam_01", "hdhcp")["action"] == "allow"
    assert engine.decide("iot_cam_01", "h90")["action"] == "deny"
