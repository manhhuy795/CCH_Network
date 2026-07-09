import ipaddress
import importlib.util
import struct
from pathlib import Path

import yaml


POLICY_PATH = Path(__file__).resolve().parents[1] / "sdn_demo" / "policy.yml"
CONTROLLER_PATH = POLICY_PATH.with_name("controller_standalone_policy.py")
TOPOLOGY_PATH = POLICY_PATH.with_name("topology_callcenter.py")
SETUP_SCRIPT_PATH = POLICY_PATH.with_name("setup_ubuntu_vm_vi.sh")


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
        "hinternet": "172.10.203.10",
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
    assert set(policy["allowed_services"]) == {"hzalo", "hcall", "hinternet"}
    assert set(policy["blocked_services"]) == {"hsocial"}
    assert ["h50", "h20"] in policy["allowed_pairs"]

    deny_pairs = {tuple(pair) for pair in policy["deny_pairs"]}
    assert ("h20", "h30") in deny_pairs
    assert ("h20", "h40") in deny_pairs
    assert ("h30", "h40") in deny_pairs
    assert ("h50", "h60") in deny_pairs


def test_standalone_controller_set_field_action_lengths_are_padded():
    spec = importlib.util.spec_from_file_location("controller_standalone_policy", CONTROLLER_PATH)
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(controller)

    action = controller.action_set_field(
        controller.OXM_ETH_DST,
        controller.mac_to_bytes("00:00:00:00:90:10"),
    )

    assert len(action) == 16
    assert struct.unpack("!H", action[2:4])[0] == 16


def test_standalone_controller_allows_controlled_intersite_pair():
    spec = importlib.util.spec_from_file_location("controller_standalone_policy", CONTROLLER_PATH)
    controller = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(controller)

    policy = controller.Policy(POLICY_PATH)

    assert ("h50", "h20") in policy.allow_pairs
    assert ("h20", "h50") in policy.allow_pairs


def test_sdn_demo_exposes_operational_commands_and_bandwidth_tooling():
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")
    setup_script = SETUP_SCRIPT_PATH.read_text(encoding="utf-8")

    for command in ("do_testsdn", "do_sdnstats", "do_sdnbw", "do_sdnblock", "do_sdnunblock"):
        assert command in topology

    assert "iperf" in setup_script
