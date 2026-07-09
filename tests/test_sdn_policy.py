import json
from pathlib import Path

from scripts.generate_sdn_policies import render_sdn_policy, validate_sdn
from scripts.common import load_vars
from sdn_mpls_demo.policy_engine import PolicyEngine


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
    assert engine.decide("h20_01", "hsocial")["blocked_at"] == "fw_hq"
    assert engine.decide("h50_01", "hsocial")["blocked_at"] == "fw_branch"
    assert "mpls_cloud" in engine.decide("h50_01", "h20_01")["path"]
