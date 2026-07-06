import ipaddress
from pathlib import Path

import yaml


POLICY_PATH = Path(__file__).resolve().parents[1] / "sdn_demo" / "policy.yml"


def load_policy():
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))


def test_sdn_demo_hosts_have_required_ips_and_unique_ports():
    policy = load_policy()
    expected_ips = {
        "h20": "172.10.20.10",
        "h30": "172.10.30.10",
        "h40": "172.10.40.10",
        "h50": "172.10.50.10",
        "h60": "172.10.60.10",
        "h90": "172.10.90.10",
        "hzalo": "172.10.200.10",
        "hcall": "172.10.201.10",
        "hsocial": "172.10.202.10",
    }

    ports = []
    for host_name, expected_ip in expected_ips.items():
        host = policy["hosts"][host_name]
        assert host["ip"] == expected_ip
        assert ipaddress.ip_interface(host["cidr"]).ip == ipaddress.ip_address(expected_ip)
        ports.append(host["switch_port"])

    assert len(ports) == len(set(ports))


def test_sdn_demo_policy_matches_required_allow_deny_model():
    policy = load_policy()

    assert policy["voice_enabled"] is True
    assert set(policy["client_hosts"]) == {"h20", "h30", "h40", "h50", "h60"}
    assert policy["voice_service"] == "h90"
    assert set(policy["allowed_services"]) == {"hzalo", "hcall"}
    assert set(policy["blocked_services"]) == {"hsocial"}

    deny_pairs = {tuple(pair) for pair in policy["deny_pairs"]}
    assert ("h20", "h30") in deny_pairs
    assert ("h20", "h40") in deny_pairs
    assert ("h30", "h40") in deny_pairs
    assert ("h50", "h60") in deny_pairs
