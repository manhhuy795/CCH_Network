from __future__ import annotations

from pathlib import Path

from sdn_mpls_demo.policy_engine import POLICY_FLOW_PROFILES


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (REPO_ROOT / "sdn_mpls_demo" / "controller_policy.py").read_text(encoding="utf-8")


def test_it_social_drop_outranks_it_service_allow():
    assert POLICY_FLOW_PROFILES["it_social_block"] == {
        "cookie": 0x1304,
        "priority": 480,
        "action": "DROP",
    }
    assert POLICY_FLOW_PROFILES["it_social_block"]["priority"] > 470
    assert 'POLICY_FLOW_PROFILES["it_social_block"]["priority"]' in CONTROLLER
    assert 'POLICY_FLOW_PROFILES["it_social_block"]["cookie"]' in CONTROLLER


def test_it_policy_is_installed_only_at_core_and_not_on_edge_devices():
    method = CONTROLLER.split("def install_it_support_flows", 1)[1].split("def install_voice_flows", 1)[0]
    assert 'if switch_name != "core_hq":' in method
    assert "fw_hq" not in method
    assert "fw_telesale" not in method
    assert "mpls_primary" not in method
    assert "mpls_backup" not in method


def test_it_icmp_directional_matches_are_explicit():
    method = CONTROLLER.split("def install_it_support_flows", 1)[1].split("def install_voice_flows", 1)[0]
    assert "icmpv4_type=ICMP_ECHO_REQUEST" in method
    assert "icmpv4_type=ICMP_ECHO_REPLY" in method
    assert '"policy": "it_inbound_block"' in method
    assert '"policy": "it_social_block"' in method
