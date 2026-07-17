from pathlib import Path

from sdn_mpls_demo.policy_engine import ICMP_ECHO_REPLY, ICMP_ECHO_REQUEST, PolicyEngine


POLICY_PATH = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"

# NHOM A: packet-path contract assert day du tung node va diem chan.

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
    assert "internet_zone" not in hq_drop["path"]
    assert "mpls_cloud" not in hq_drop["path"]

    social_drop = policy.decide("h40_01", "hsocial")
    assert_stops_at(social_drop, "core_hq")
    assert "fw_hq" not in social_drop["path"]
    assert "internet_zone" not in social_drop["path"]

    branch_drop = policy.decide("h50_01", "h60_01")
    assert_stops_at(branch_drop, "dist_telesale")
    assert "fw_telesale" not in branch_drop["path"]
    assert "internet_zone" not in branch_drop["path"]
    assert "mpls_cloud" not in branch_drop["path"]

    branch_social = policy.decide("h50_01", "hsocial")
    assert_stops_at(branch_social, "dist_telesale")
    assert "fw_telesale" not in branch_social["path"]
    assert "internet_zone" not in branch_social["path"]


def test_allowed_service_paths_use_the_correct_site_firewall_only():
    policy = engine()

    hq_call = policy.decide("h20_01", "hcall")
    assert hq_call["action"] == "allow"
    assert hq_call["path"] == ["project_a", "access_hq_a", "core_hq", "fw_hq", "internet_zone", "hcall"]
    assert "mpls_cloud" not in hq_call["path"]
    assert "fw_telesale" not in hq_call["path"]

    branch_call = policy.decide("h50_01", "hcall")
    assert branch_call["action"] == "allow"
    assert branch_call["path"] == ["telesale", "access_telesale", "dist_telesale", "fw_telesale", "internet_zone", "hcall"]
    assert "mpls_cloud" not in branch_call["path"]
    assert "fw_hq" not in branch_call["path"]

    backoffice_call = policy.decide("h60_01", "hcall")
    assert backoffice_call["action"] == "allow"
    assert backoffice_call["path"] == ["backoffice", "access_backoffice", "core_hq", "fw_hq", "internet_zone", "hcall"]
    assert "fw_telesale" not in backoffice_call["path"]


def test_voice_and_it_support_paths_use_mpls_only_when_cross_site():
    policy = engine()

    hq_voice = policy.decide("h20_01", "h90")
    assert hq_voice["path"] == ["project_a", "access_hq_a", "core_hq", "voice_access", "h90"]
    assert "mpls_cloud" not in hq_voice["path"]

    branch_voice = policy.decide("h50_01", "h90")
    assert branch_voice["path"] == [
        "telesale",
        "access_telesale",
        "dist_telesale",
        "ce_telesale",
        "mpls_cloud",
        "ce_hq",
        "core_hq",
        "voice_access",
        "h90",
    ]
    assert "fw_hq" not in branch_voice["path"]
    assert "fw_telesale" not in branch_voice["path"]

    backoffice_voice = policy.decide("h60_01", "h90")
    assert backoffice_voice["path"] == [
        "backoffice", "access_backoffice", "core_hq", "voice_access", "h90"
    ]
    assert not {"mpls_cloud", "ce_telesale", "fw_hq", "fw_telesale"} & set(backoffice_voice["path"])

    it_to_branch = policy.decide("h70_01", "h50_01")
    assert it_to_branch["action"] == "allow"
    assert it_to_branch["path"] == [
        "it_support",
        "access_hq_it",
        "core_hq",
        "ce_hq",
        "mpls_cloud",
        "ce_telesale",
        "dist_telesale",
        "access_telesale",
        "telesale",
    ]
    assert "fw_hq" not in it_to_branch["path"]
    assert "fw_telesale" not in it_to_branch["path"]


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
    assert_stops_at(inbound, "internet_zone")
    assert inbound["path"] == ["hinternet", "internet_zone"]

    allowed_reply = policy.decide_packet("hcall", "h50_01", icmp_type=ICMP_ECHO_REPLY)
    assert allowed_reply["action"] == "allow"
    assert allowed_reply["path"] == ["hcall", "internet_zone", "fw_telesale", "dist_telesale", "access_telesale", "telesale"]

    blocked_reply = policy.decide_packet("hsocial", "h20_01", icmp_type=ICMP_ECHO_REPLY)
    assert blocked_reply["action"] == "deny"
    assert blocked_reply["blocked_at"] == "internet_zone"
    assert blocked_reply["path"] == ["hsocial", "internet_zone"]


def test_it_support_return_path_is_reply_only():
    policy = engine()

    request = policy.decide_packet("h20_01", "h70_01", icmp_type=ICMP_ECHO_REQUEST)
    assert request["action"] == "deny"

    reply = policy.decide_packet("h20_01", "h70_01", icmp_type=ICMP_ECHO_REPLY)
    assert reply["action"] == "allow"
    assert reply["path"] == ["project_a", "access_hq_a", "core_hq", "access_hq_it", "it_support"]


def test_phase27_required_packet_path_matrix():
    policy = engine()

    cases = {
        ("h20_01", "h30_01"): "core_hq",
        ("h50_01", "h60_01"): "dist_telesale",
        ("h60_01", "h50_01"): "core_hq",
        ("h20_01", "hsocial"): "core_hq",
        ("h50_01", "hsocial"): "dist_telesale",
    }
    for pair, blocked_at in cases.items():
        decision = policy.decide(*pair)
        assert_stops_at(decision, blocked_at)

    assert "fw_hq" in policy.decide("h20_01", "hcall")["path"]
    assert "fw_telesale" in policy.decide("h50_01", "hcall")["path"]
    intersite = policy.decide("h50_01", "h20_01")
    assert intersite["path"] == ["telesale", "access_telesale", "dist_telesale"]
    for allowed_cross_site in (policy.decide("h50_01", "h90"), policy.decide("h70_01", "h50_01")):
        assert "ce_telesale" in allowed_cross_site["path"]
        assert "mpls_cloud" in allowed_cross_site["path"]
        assert "ce_hq" in allowed_cross_site["path"]
