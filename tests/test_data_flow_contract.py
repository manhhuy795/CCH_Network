from pathlib import Path

from sdn_mpls_demo.policy_engine import PolicyEngine


def test_required_enterprise_data_flows():
    engine = PolicyEngine(Path("sdn_mpls_demo/policy.yml"))
    cases = {
        ("guest_01", "hinternet"): "allow",
        ("guest_01", "h20_01"): "deny",
        ("iot_cam_01", "hnvr"): "allow",
        ("iot_branch_cam_01", "hmonitor"): "allow",
        ("h50_01", "h90"): "allow",
        ("h50_01", "hdialer"): "allow",
        ("h60_01", "h90"): "allow",
        ("h20_01", "hsocial"): "deny",
    }
    for (source, destination), expected in cases.items():
        decision = engine.decide(source, destination)
        assert decision["action"] == expected, (source, destination, decision)
        assert decision["path"]
        if expected == "deny":
            assert decision["blocked_at"]


def test_ups_is_not_in_corporate_user_paths():
    engine = PolicyEngine(Path("sdn_mpls_demo/policy.yml"))
    decision = engine.decide("h20_01", "hmonitor")
    assert "ups_floor1" not in decision["path"]
    assert "ups_core_1" not in decision["path"]
