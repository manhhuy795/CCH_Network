from pathlib import Path

from sdn_mpls_demo.policy_engine import ICMP_ECHO_REPLY, ICMP_ECHO_REQUEST, PolicyEngine


POLICY_PATH = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"


def engine() -> PolicyEngine:
    return PolicyEngine(POLICY_PATH)


def assert_stops_at(decision: dict, node: str) -> None:
    assert decision["action"] == "deny"
    assert decision["blocked_at"] == node
    assert decision["path"][-1] == node


def test_policy_drop_paths_stop_before_firewall_or_mpls():
    policy = engine()

    hq_drop = policy.decide("h20_01", "h30_01")
    assert_stops_at(hq_drop, "core_hq")
    assert "fw_hq" not in hq_drop["path"]
    assert "internet" not in hq_drop["path"]
    assert "mpls_cloud" not in hq_drop["path"]

    social_drop = policy.decide("h40_01", "hsocial")
    assert_stops_at(social_drop, "core_hq")
    assert "fw_hq" not in social_drop["path"]
    assert "internet" not in social_drop["path"]

    branch_drop = policy.decide("h50_01", "h60_01")
    assert_stops_at(branch_drop, "dist_branch")
    assert "fw_branch" not in branch_drop["path"]
    assert "internet" not in branch_drop["path"]
    assert "mpls_cloud" not in branch_drop["path"]

    branch_social = policy.decide("h50_01", "hsocial")
    assert_stops_at(branch_social, "dist_branch")
    assert "fw_branch" not in branch_social["path"]
    assert "internet" not in branch_social["path"]


def test_allowed_service_paths_use_the_correct_site_firewall_only():
    policy = engine()

    hq_call = policy.decide("h20_01", "hcall")
    assert hq_call["action"] == "allow"
    assert hq_call["path"] == ["project_a", "access_hq_a", "core_hq", "fw_hq", "internet", "hcall"]
    assert "mpls_cloud" not in hq_call["path"]
    assert "fw_branch" not in hq_call["path"]

    branch_call = policy.decide("h50_01", "hcall")
    assert branch_call["action"] == "allow"
    assert branch_call["path"] == ["telesale", "access_branch", "dist_branch", "fw_branch", "internet", "hcall"]
    assert "mpls_cloud" not in branch_call["path"]
    assert "fw_hq" not in branch_call["path"]


def test_voice_and_it_support_paths_use_mpls_only_when_cross_site():
    policy = engine()

    hq_voice = policy.decide("h20_01", "h90")
    assert hq_voice["path"] == ["project_a", "access_hq_a", "core_hq", "voice_access", "h90"]
    assert "mpls_cloud" not in hq_voice["path"]

    branch_voice = policy.decide("h50_01", "h90")
    assert branch_voice["path"] == [
        "telesale",
        "access_branch",
        "dist_branch",
        "ce_branch",
        "mpls_cloud",
        "ce_hq",
        "core_hq",
        "voice_access",
        "h90",
    ]

    it_to_branch = policy.decide("h70_01", "h50_01")
    assert it_to_branch["action"] == "allow"
    assert it_to_branch["path"] == [
        "it_support",
        "access_hq_it",
        "core_hq",
        "ce_hq",
        "mpls_cloud",
        "ce_branch",
        "dist_branch",
        "access_branch",
        "telesale",
    ]
    assert "fw_hq" not in it_to_branch["path"]
    assert "fw_branch" not in it_to_branch["path"]


def test_controller_is_not_in_any_data_path():
    policy = engine()
    cases = (
        ("h20_01", "h90"),
        ("h20_01", "h30_01"),
        ("h50_01", "hcall"),
        ("h70_01", "h50_01"),
        ("hinternet", "h20_01"),
    )
    for source, destination in cases:
        assert "c0" not in policy.decide(source, destination)["path"]


def test_internet_inbound_and_return_traffic_paths_are_explicit():
    policy = engine()

    inbound = policy.decide_packet("hinternet", "h20_01", icmp_type=ICMP_ECHO_REQUEST)
    assert_stops_at(inbound, "internet")
    assert inbound["path"] == ["hinternet", "internet"]

    allowed_reply = policy.decide_packet("hcall", "h50_01", icmp_type=ICMP_ECHO_REPLY)
    assert allowed_reply["action"] == "allow"
    assert allowed_reply["path"] == ["hcall", "internet", "fw_branch", "dist_branch", "access_branch", "telesale"]

    blocked_reply = policy.decide_packet("hsocial", "h20_01", icmp_type=ICMP_ECHO_REPLY)
    assert blocked_reply["action"] == "deny"
    assert blocked_reply["blocked_at"] == "internet"
    assert blocked_reply["path"] == ["hsocial", "internet"]


def test_it_support_return_path_is_reply_only():
    policy = engine()

    request = policy.decide_packet("h20_01", "h70_01", icmp_type=ICMP_ECHO_REQUEST)
    assert request["action"] == "deny"

    reply = policy.decide_packet("h20_01", "h70_01", icmp_type=ICMP_ECHO_REPLY)
    assert reply["action"] == "allow"
    assert reply["path"] == ["project_a", "access_hq_a", "core_hq", "access_hq_it", "it_support"]
