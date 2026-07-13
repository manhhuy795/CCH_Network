import json
from pathlib import Path

from scripts.generate_sdn_policies import render_sdn_policy, validate_sdn
from scripts.common import load_vars
from sdn_mpls_demo.policy_engine import ICMP_ECHO_REPLY, ICMP_ECHO_REQUEST, PolicyEngine


def test_sdn_intents_reference_known_vlans_and_devices():
    config = load_vars()
    assert validate_sdn(config) == []


def test_sdn_policy_renders_valid_json(tmp_path: Path):
    path = render_sdn_policy(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["metadata"]["name"] == "callcenter-bpo-sdn-intents"
    assert "hq-core-l3" in payload["fabric_scope"]
    assert any(intent["name"] == "isolate-hq-project-a" for intent in payload["intents"])
    assert any(boundary["name"] == "mpls_l3vpn" for boundary in payload["protected_boundaries"])


def test_real_sdn_policy_required_allow_deny_paths():
    policy_path = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"
    engine = PolicyEngine(policy_path)

    assert engine.decide("h20_01", "h30_01")["action"] == "deny"
    assert engine.decide("h20_01", "h90")["action"] == "allow"
    assert engine.decide("h20_01", "hcall")["path"][-3:] == ["fw_hq", "internet", "hcall"]
    assert engine.decide("h50_01", "hcall")["path"][-3:] == ["fw_branch", "internet", "hcall"]
    assert engine.decide("h20_01", "hsocial")["blocked_at"] == "core_hq"
    assert engine.decide("h50_01", "hsocial")["blocked_at"] == "dist_branch"
    intersite_user = engine.decide("h50_01", "h20_01")
    assert intersite_user["action"] == "deny"
    assert intersite_user["blocked_at"] == "dist_branch"


def test_all_user_groups_can_reach_voice_service():
    policy_path = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"
    engine = PolicyEngine(policy_path)

    for source in ("h20_01", "h30_01", "h40_01", "h50_01", "h60_01", "h70_01"):
        decision = engine.decide(source, "h90")
        assert decision["action"] == "allow"
        if source != "h70_01":
            assert decision["voice_flow_priority"] is True
        assert decision["path"][-2:] == ["voice_access", "h90"]


def test_internet_cannot_initiate_ping_to_inside_users():
    policy_path = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"
    engine = PolicyEngine(policy_path)

    assert engine.decide("hinternet", "h20_01")["action"] == "deny"
    assert engine.decide_packet("hinternet", "h20_01", icmp_type=ICMP_ECHO_REQUEST)["action"] == "deny"
    assert engine.decide_packet("hcall", "h50_01", icmp_type=ICMP_ECHO_REQUEST)["action"] == "deny"
    assert engine.decide_packet("hinternet", "h70_01", icmp_type=ICMP_ECHO_REQUEST)["action"] == "deny"


def test_icmp_replies_from_allowed_services_are_permitted():
    policy_path = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"
    engine = PolicyEngine(policy_path)

    assert engine.decide_packet("hinternet", "h20_01", icmp_type=ICMP_ECHO_REPLY)["action"] == "allow"
    assert engine.decide_packet("hcall", "h50_01", icmp_type=ICMP_ECHO_REPLY)["action"] == "allow"
    assert engine.decide_packet("hsocial", "h20_01", icmp_type=ICMP_ECHO_REPLY)["action"] == "deny"
