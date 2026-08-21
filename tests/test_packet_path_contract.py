from pathlib import Path

from sdn_mpls_demo.policy_engine import ICMP_ECHO_REPLY, ICMP_ECHO_REQUEST, PolicyEngine


POLICY_PATH = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"


def engine() -> PolicyEngine:
    return PolicyEngine(POLICY_PATH)


def assert_stops_at(decision: dict, node: str) -> None:
    assert decision["action"] == "deny"
    assert decision["blocked_at"] == node
    assert decision["path"][-1] == node


def test_sdn_isolation_stops_before_firewall_and_branch_distribution():
    policy = engine()
    assert_stops_at(policy.decide("h20_01", "h30_01"), "core_hq")
    assert_stops_at(policy.decide("h50_01", "h60_01"), "dist_branch")
    assert_stops_at(policy.decide("h50_01", "hsocial"), "fw_telesale")
    for source, destination in (("h20_01", "h30_01"), ("h50_01", "h60_01")):
        decision = policy.decide(source, destination)
        assert "internet_zone" not in decision["path"]
        assert "fw_hq" not in decision["path"]
        assert "fw_telesale" not in decision["path"]


def test_allowed_service_paths_use_the_correct_site_firewall_only():
    policy = engine()
    assert policy.decide("h20_01", "hcall")["path"] == [
        "project_a", "access_floor1", "dist_hq_1", "core_hq", "fw_hq", "internet_zone", "hcall"
    ]
    assert policy.decide("h50_01", "hcall")["path"] == [
        "telesale", "access_branch", "dist_branch", "fw_telesale", "internet_zone", "hcall"
    ]
    assert policy.decide("h60_01", "hcall")["path"][-3:] == ["fw_hq", "internet_zone", "hcall"]


def test_voice_and_monitoring_paths_use_infrastructure_and_mpls():
    policy = engine()
    assert policy.decide("h20_01", "h90")["path"] == [
        "project_a", "access_floor1", "dist_hq_1", "core_hq", "infra_access", "h90"
    ]
    assert policy.decide("h50_01", "h90")["path"] == [
        "telesale", "access_branch", "dist_branch", "ce_telesale", "mpls_primary",
        "ce_hq", "core_hq", "infra_access", "h90"
    ]
    branch_iot = policy.decide("iot_branch_cam_01", "hmonitor")
    assert branch_iot["action"] == "allow"
    assert branch_iot["path"][-5:] == ["mpls_primary", "ce_hq", "core_hq", "infra_access", "hmonitor"]
    assert "fw_telesale" not in branch_iot["path"]


def test_project_b_floor_two_path_is_not_hardcoded_to_floor_one():
    policy = engine()
    floor_one = policy.decide("h30_01", "h90")
    floor_two = policy.decide("h30_11", "h90")
    assert floor_one["path"][1:3] == ["access_floor1", "dist_hq_1"]
    assert floor_two["path"][1:3] == ["access_floor2", "dist_hq_2"]


def test_internet_inbound_and_return_traffic_paths_are_explicit():
    policy = engine()
    inbound = policy.decide_packet("hinternet", "h20_01", icmp_type=ICMP_ECHO_REQUEST)
    assert_stops_at(inbound, "fw_hq")
    assert inbound["path"] == ["hinternet", "internet_zone", "fw_hq"]

    allowed_reply = policy.decide_packet("hcall", "h50_01", icmp_type=ICMP_ECHO_REPLY)
    assert allowed_reply["action"] == "allow"
    assert allowed_reply["path"] == ["hcall", "internet_zone", "fw_telesale", "dist_branch", "access_branch", "telesale"]

    blocked_reply = policy.decide_packet("hsocial", "h20_01", icmp_type=ICMP_ECHO_REPLY)
    assert_stops_at(blocked_reply, "fw_hq")


def test_it_support_icmp_is_least_privilege():
    policy = engine()
    assert policy.decide_packet("h70_01", "h20_01", icmp_type=ICMP_ECHO_REQUEST)["action"] == "allow"
    assert policy.decide_packet("h20_01", "h70_01", icmp_type=ICMP_ECHO_REQUEST)["action"] == "deny"
    reply = policy.decide_packet("h20_01", "h70_01", icmp_type=ICMP_ECHO_REPLY)
    assert reply["action"] == "allow"
    assert reply["path"] == ["project_a", "access_floor1", "dist_hq_1", "core_hq", "dist_hq_2", "access_floor2", "it_support"]
    assert policy.decide("h70_01", "hsocial")["action"] == "deny"


def test_controller_is_not_in_any_data_path():
    policy = engine()
    for source, destination in (("h20_01", "h90"), ("h20_01", "h30_01"), ("h50_01", "hcall"), ("h70_01", "h50_01")):
        assert "c0" not in policy.decide(source, destination)["path"]


def test_required_path_matrix_and_enforcement_points():
    policy = engine()
    cases = {
        ("h20_01", "h30_01"): "core_hq",
        ("h50_01", "h60_01"): "dist_branch",
        ("h60_01", "h50_01"): "core_hq",
        ("h20_01", "hsocial"): "fw_hq",
        ("h50_01", "hsocial"): "fw_telesale",
        ("guest_01", "h20_01"): "core_hq",
    }
    for pair, blocked_at in cases.items():
        assert_stops_at(policy.decide(*pair), blocked_at)
    assert "fw_hq" in policy.decide("h20_01", "hcall")["path"]
    assert "fw_telesale" in policy.decide("h50_01", "hcall")["path"]
