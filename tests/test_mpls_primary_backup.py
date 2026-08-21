from pathlib import Path

from scripts.network_model import load_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine


def test_mpls_clouds_are_independent_with_primary_preference():
    model = load_network_model()
    links = model["links"]
    assert model["infrastructure"]["mpls_primary"]["metric"] == 10
    assert model["infrastructure"]["mpls_backup"]["metric"] == 100
    assert ["ce_hq", "mpls_primary", "ce_telesale", "mpls_backup"] not in links
    assert {tuple(link[:2]) for link in links if link[2] == "mpls"} == {
        ("ce_hq", "mpls_primary"), ("mpls_primary", "ce_telesale"),
        ("ce_hq", "mpls_backup"), ("mpls_backup", "ce_telesale"),
    }


def test_telesale_voice_path_uses_primary_and_declares_backup():
    model = load_network_model()
    engine = PolicyEngine(Path("sdn_mpls_demo/policy.yml"))
    decision = engine.decide("h50_01", "h90")
    assert decision["action"] == "allow"
    assert "mpls_primary" in decision["path"]
    assert model["reference_paths"]["telesale_voice_backup"][4] == "mpls_backup"
