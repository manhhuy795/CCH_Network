from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from scripts.common import load_vars
from scripts.validate_vars import validate_all
from sdn_mpls_demo.firewall_nftables import (
    FIREWALL_NAMES,
    NFT_FAMILY,
    NFT_TABLE,
    apply_to_mininet,
    build_firewall_plans,
    render_nftables_ruleset,
)
from sdn_mpls_demo.policy_engine import PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
CONTROLLER_PATH = REPO_ROOT / "sdn_mpls_demo" / "controller_policy.py"
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"


# GROUP A: every test asserts concrete ownership, match, action or runtime placement.


def test_phase44_only_two_firewall_namespaces_have_exact_interfaces_and_ownership():
    plans = build_firewall_plans()

    assert set(plans) == set(FIREWALL_NAMES) == {"fw_hq", "fw_telesale"}
    assert plans["fw_hq"]["inside_interface"] == "fw_hq-eth0"
    assert plans["fw_hq"]["outside_interface"] == "fw_hq-eth1"
    assert set(plans["fw_hq"]["owned_subnets"]) == {
        "172.16.20.0/24",
        "172.16.30.0/24",
        "172.16.40.0/24",
        "172.16.60.0/24",
        "172.16.70.0/24",
        "172.16.80.0/24",
        "172.16.110.0/24",
    }
    assert plans["fw_telesale"]["inside_interface"] == "fw_tel-eth0"
    assert plans["fw_telesale"]["outside_interface"] == "fw_tel-eth1"
    assert plans["fw_telesale"]["owned_subnets"] == ("172.16.50.0/24",)
    assert not {"fw_branch", "fw_backoffice"} & set(plans)


def test_phase44_stateful_default_deny_and_inbound_rules_are_explicit_per_firewall():
    for firewall_name, plan in build_firewall_plans().items():
        ruleset = render_nftables_ruleset(plan)
        assert f"table {NFT_FAMILY} {NFT_TABLE}" in ruleset
        assert "type filter hook input priority 0; policy drop;" in ruleset
        assert "type filter hook forward priority 0; policy drop;" in ruleset
        assert "type filter hook output priority 0; policy accept;" in ruleset
        assert "ct state invalid counter drop" in ruleset
        assert "ct state established,related counter accept" in ruleset
        assert f'iifname "{plan["outside_interface"]}" oifname "{plan["inside_interface"]}"' in ruleset
        assert f'comment "cch:{firewall_name}:deny-inbound-new"' in ruleset
        assert f'comment "cch:{firewall_name}:forward-default-deny"' in ruleset


def test_phase44_service_rules_have_exact_source_destination_action_counter_and_site():
    plans = build_firewall_plans()
    expected = {
        "allow-zalo": ("allow", "hzalo", "172.16.200.10/32"),
        "allow-call-app": ("allow", "hcall", "172.16.201.10/32"),
        "deny-social-media": ("deny", "hsocial", "172.16.202.10/32"),
        "allow-general-internet": ("allow", "hinternet", "172.16.203.10/32"),
    }
    for firewall_name, plan in plans.items():
        by_name = {rule["name"]: rule for rule in plan["rules"]}
        expected_names = set(expected) | ({"allow-guest-general-internet"} if firewall_name == "fw_hq" else set())
        assert set(by_name) == expected_names
        for name, (action, service, destination_ip) in expected.items():
            rule = by_name[name]
            assert rule["firewall"] == firewall_name
            assert rule["action"] == action
            assert rule["destination_service"] == service
            assert rule["destination_ip"] == destination_ip
            assert rule["counter"] is True
            assert rule["comment"] == f"cch:{firewall_name}:{name}:{service}"
        expected_sources = (
            {"172.16.50.0/24"}
            if firewall_name == "fw_telesale"
            else {"172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.60.0/24", "172.16.70.0/24"}
        )
        for rule in plan["rules"]:
            if firewall_name == "fw_hq" and rule["name"] == "allow-guest-general-internet":
                assert set(rule["source_subnets"]) == {"172.16.80.0/24"}
            else:
                assert set(rule["source_subnets"]) == expected_sources


def test_phase44_render_and_reload_identity_are_deterministic_without_duplicate_or_nat():
    first = build_firewall_plans()
    second = build_firewall_plans()
    assert first == second
    for firewall_name in FIREWALL_NAMES:
        first_ruleset = render_nftables_ruleset(first[firewall_name])
        second_ruleset = render_nftables_ruleset(second[firewall_name])
        assert first_ruleset == second_ruleset
        comments = [line.split('comment "', 1)[1].rsplit('"', 1)[0] for line in first_ruleset.splitlines() if 'comment "' in line]
        expected_comment_count = 14 if firewall_name == "fw_hq" else 13
        assert len(comments) == len(set(comments)) == expected_comment_count
        assert "masquerade" not in first_ruleset.lower()
        assert " snat " not in first_ruleset.lower()
        assert first[firewall_name]["nat"] == {
            "enabled": False,
            "mode": "routed_lab",
            "runtime_verification_required": True,
            "reason": "Internet Zone va service hosts co route tra ve tung subnet noi bo qua dung firewall site.",
        }


def test_phase44_apply_twice_replaces_the_same_table_without_rule_growth(tmp_path):
    plans = build_firewall_plans()

    class FakeNode:
        def __init__(self, name: str) -> None:
            self.name = name
            self.commands: list[str] = []

        def cmd(self, command: str) -> str:
            self.commands.append(command)
            ruleset = render_nftables_ruleset(plans[self.name]) if "list table" in command else ""
            return f"{ruleset}\n__CCH_NFT_EXIT__=0\n"

    class FakeNet:
        def __init__(self) -> None:
            self.nodes = {name: FakeNode(name) for name in FIREWALL_NAMES}

        def get(self, name: str) -> FakeNode:
            return self.nodes[name]

    net = FakeNet()
    first = apply_to_mininet(net, tmp_path)
    second = apply_to_mininet(net, tmp_path)

    assert {name: item["rule_count"] for name, item in first.items()} == {
        "fw_hq": 14,
        "fw_telesale": 13,
    }
    assert {name: item["rule_count"] for name, item in second.items()} == {
        "fw_hq": 14,
        "fw_telesale": 13,
    }
    for node in net.nodes.values():
        replacements = [command for command in node.commands if "nft delete table inet cch_filter" in command]
        syntax_checks = [command for command in node.commands if "nft --check --file" in command]
        assert len(replacements) == len(syntax_checks) == 2
        assert all("nft --file" in command for command in replacements)


def test_phase44_voice_bypasses_firewall_and_cross_site_isolation_remains_openflow():
    engine = PolicyEngine(POLICY_PATH)
    backoffice_voice = engine.decide("h60_01", "h90")
    telesale_voice = engine.decide("h50_01", "h90")
    assert backoffice_voice["path"] == ["backoffice", "access_backoffice", "core_hq", "voice_access", "h90"]
    assert not {"fw_hq", "fw_telesale", "mpls_cloud"} & set(backoffice_voice["path"])
    assert telesale_voice["path"] == [
        "telesale", "access_telesale", "dist_telesale", "ce_telesale",
        "mpls_cloud", "ce_hq", "core_hq", "voice_access", "h90",
    ]
    assert not {"fw_hq", "fw_telesale"} & set(telesale_voice["path"])
    assert engine.decide("h50_01", "h60_01")["blocked_at"] == "dist_telesale"
    assert engine.decide("h60_01", "h50_01")["blocked_at"] == "core_hq"


def test_phase44_social_and_inbound_paths_stop_at_the_correct_nftables_firewall():
    engine = PolicyEngine(POLICY_PATH)
    cases = {
        ("h20_01", "hsocial"): ("fw_hq", ["project_a", "access_hq_a", "core_hq", "fw_hq"]),
        ("h60_01", "hsocial"): ("fw_hq", ["backoffice", "access_backoffice", "core_hq", "fw_hq"]),
        ("h50_01", "hsocial"): ("fw_telesale", ["telesale", "access_telesale", "dist_telesale", "fw_telesale"]),
        ("hinternet", "h20_01"): ("fw_hq", ["hinternet", "internet_zone", "fw_hq"]),
        ("hcall", "h50_01"): ("fw_telesale", ["hcall", "internet_zone", "fw_telesale"]),
    }
    for pair, (firewall, path) in cases.items():
        decision = engine.decide(*pair)
        assert decision["action"] == "deny"
        assert decision["blocked_at"] == firewall
        assert decision["enforcement_point"] == firewall
        assert decision["path"] == path


def test_phase44_controller_does_not_install_internet_firewall_policy_on_ovs():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")
    install_body = controller.split("def install_policy_flows", 1)[1].split("def install_arp_transit_flow", 1)[0]
    it_body = controller.split("def install_it_support_flows", 1)[1].split("def install_voice_flows", 1)[0]

    assert "self.install_isolation_flows(datapath)" in install_body
    assert "self.install_voice_flows(datapath)" in install_body
    assert "self.install_it_support_flows(datapath)" in install_body
    assert "install_service_policy_flows" not in install_body
    assert it_body.index("return\n") < it_body.index("for destination_name, destination_prefix in service_destinations")


def test_phase44_topology_applies_only_two_firewalls_and_enables_forwarding_on_routers():
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")
    apply_body = topology.split("firewall_status = apply_to_mininet(net)", 1)[0]
    assert "expose_named_firewall_namespaces(net)" in apply_body
    assert "sysctl -w net.ipv4.ip_forward=1" in topology
    assert 'net.addHost("fw_hq", cls=LinuxRouter' in topology
    assert 'net.addHost("fw_telesale", cls=LinuxRouter' in topology
    for forbidden in ("fw_branch", "fw_backoffice"):
        assert f'net.addHost("{forbidden}"' not in topology


def test_phase44_validation_rejects_nat_without_proof_and_wrong_firewall_interface():
    config = deepcopy(load_vars())
    config["firewall_policy"]["runtime_defaults"]["nat"]["enabled"] = True
    config["firewall_policy"]["sites"]["hq"]["runtime_interfaces"]["inside"] = "core_hq"
    errors = validate_all(config)
    assert any("NAT must remain disabled" in error for error in errors)
    assert any("hq has incorrect runtime interfaces" in error for error in errors)


# GROUP B: structural readiness of the Ubuntu-only runner; it does not claim live PASS.
def test_phase44_runtime_checker_covers_required_live_evidence_without_shell_true():
    source = (REPO_ROOT / "scripts" / "phase44_firewall_runtime_check.py").read_text(encoding="utf-8")
    for required in (
        "Mininet Control Agent HEALTH",
        "Twelve OVS connected",
        "HQ Project A -> Call",
        "BackOffice -> Social",
        "Telesale -> Zalo",
        "Internet -> Telesale",
        "BackOffice -> Voice",
        "Telesale -> BackOffice OpenFlow",
        "idempotent reload",
        "NAT source capture",
        "Runtime error scan",
    ):
        assert required in source
    assert "shell=True" not in source
    assert "NAT NOT REQUIRED AND RUNTIME PROVEN" in source
    assert "NAT REQUIREMENT NOT YET CONCLUDED" in source


def test_phase44_runtime_checker_allows_finalize_transfer_branch():
    source = (REPO_ROOT / "scripts" / "phase44_firewall_runtime_check.py").read_text(encoding="utf-8")
    assert '"transfer/phase45-regression-fix"' in source
    assert 'branch_name in ALLOWED_RUNTIME_BRANCHES' in source
