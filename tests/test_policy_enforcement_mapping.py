from pathlib import Path

from sdn_mpls_demo.policy_engine import PolicyEngine


def test_enforcement_points_match_layers_and_firewalls():
    engine = PolicyEngine(Path("sdn_mpls_demo/policy.yml"))
    assert engine.decide("h20_01", "h30_01")["blocked_at"] == "core_hq"
    assert engine.decide("h50_01", "h60_01")["blocked_at"] == "dist_branch"
    assert engine.decide("h20_01", "hsocial")["blocked_at"] == "fw_hq"
    assert engine.decide("h50_01", "hsocial")["blocked_at"] == "fw_telesale"
    assert engine.decide("h20_01", "h70_01")["blocked_at"] == "core_hq"
    assert engine.decide("h70_01", "h20_01")["action"] == "allow"
