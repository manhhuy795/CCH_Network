import re
from pathlib import Path

import yaml

from sdn_mpls_demo.policy_engine import PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"
CONTROLLER_PATH = REPO_ROOT / "sdn_mpls_demo" / "controller_policy.py"


def test_hybrid_topology_has_one_hundred_four_users_and_five_services():
    engine = PolicyEngine(POLICY_PATH)
    users = [host for host in engine.hosts.values() if host["kind"] == "user"]
    services = [host for host in engine.hosts.values() if host["kind"] == "service"]

    assert len(users) == 104
    assert len(services) == 5
    assert engine.hosts["h20_01"]["ip"] == "172.16.20.11"
    assert engine.hosts["h70_04"]["ip"] == "172.16.70.14"
    assert "h70_05" not in engine.hosts
    assert engine.hosts["h60_20"]["ip"] == "172.16.60.30"


def test_topology_forces_intersite_path_through_ce_and_mpls():
    source = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert 'switches["core_hq"], ce_hq,' in source
    assert "ce_hq, mpls_cloud," in source
    assert "ce_branch, mpls_cloud," in source
    assert 'switches["dist_branch"], ce_branch,' in source
    assert 'net.addLink(switches["dist_branch"], switches["core_hq"]' not in source
    assert 'intfName2=f"{group[\'prefix\']}-u{index:02d}"' in source
    assert 'intfName1="br-eth99"' in source
    assert 'intfName2="dist-eth01"' in source

    explicit_interfaces = re.findall(r'intfName[12]="([^"]+)"', source)
    assert explicit_interfaces
    assert all(len(name) <= 15 for name in explicit_interfaces)
    assert all("-eth" in name for name in explicit_interfaces)


def test_only_expected_ovs_are_controller_managed():
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert policy["runtime"]["controller"] == "127.0.0.1:6653"
    for switch in (
        "access_hq_a", "access_hq_b", "access_hq_c", "voice_mgmt",
        "core_hq", "access_branch", "dist_branch", "access_hq_it",
    ):
        assert f'"{switch}"' in topology
    assert '"mpls_cloud",' in topology
    assert 'dpid="00000000000000f1"' in topology
    assert '"internet",' in topology
    assert 'dpid="00000000000000f2"' in topology


def test_controller_is_real_osken_openflow_13_app():
    controller = CONTROLLER_PATH.read_text(encoding="utf-8")

    assert "app_manager.OSKenApp" in controller
    assert "ofproto_v1_3.OFP_VERSION" in controller
    assert "EventOFPPacketIn" in controller
    assert "OFPFlowMod" in controller
    assert "installed_flows.json" in controller
    assert "install_isolation_flows" in controller
    assert "priority=400" in (
        REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"
    ).read_text(encoding="utf-8")


def test_topology_runner_auto_starts_and_waits_for_controller():
    runner = (REPO_ROOT / "sdn_mpls_demo" / "run_topology.sh").read_text(encoding="utf-8")

    assert "controller_is_listening" in runner
    assert "run_controller.sh" in runner
    assert "CONTROLLER_LOG" in runner
    assert "tail -n 40" in runner
    assert "os_ken.cmd.manager|osken-manager" not in runner
    assert "flock -n 9" in runner
    assert "[t]opology_hybrid_sdn.py" in runner
    assert "cleanup_stale_network" in runner
    assert "hqa-core" in runner
    assert "hqa-eth99" in runner


def test_osken_version_keeps_controller_cli():
    requirements = (REPO_ROOT / "sdn_mpls_demo" / "requirements.txt").read_text(encoding="utf-8")
    setup = (REPO_ROOT / "sdn_mpls_demo" / "setup_ubuntu_24_04.sh").read_text(encoding="utf-8")

    assert "os-ken==3.1.1" in requirements
    assert "os_ken.cmd.manager" in setup
    assert "osken-manager" in setup
