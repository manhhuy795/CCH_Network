import json
from pathlib import Path

from scripts.generate_sdn_policies import render_sdn_policy, validate_sdn
from scripts.common import load_vars


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
