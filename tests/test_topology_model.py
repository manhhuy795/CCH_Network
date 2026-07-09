from pathlib import Path

import yaml

from sdn_mpls_demo.policy_engine import PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"


def test_hybrid_topology_has_one_hundred_users_and_five_services():
    engine = PolicyEngine(POLICY_PATH)
    users = [host for host in engine.hosts.values() if host["kind"] == "user"]
    services = [host for host in engine.hosts.values() if host["kind"] == "service"]

    assert len(users) == 100
    assert len(services) == 5
    assert engine.hosts["h20_01"]["ip"] == "172.16.20.11"
    assert engine.hosts["h60_20"]["ip"] == "172.16.60.30"


def test_topology_forces_intersite_path_through_ce_and_mpls():
    source = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert 'net.addLink(switches["core_hq"], ce_hq' in source
    assert "net.addLink(ce_hq, mpls_cloud" in source
    assert "net.addLink(ce_branch, mpls_cloud" in source
    assert 'net.addLink(switches["dist_branch"], ce_branch' in source
    assert 'net.addLink(switches["dist_branch"], switches["core_hq"]' not in source


def test_only_expected_ovs_are_controller_managed():
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    topology = TOPOLOGY_PATH.read_text(encoding="utf-8")

    assert policy["runtime"]["controller"] == "127.0.0.1:6653"
    for switch in (
        "access_hq_a", "access_hq_b", "access_hq_c", "voice_mgmt",
        "core_hq", "access_branch", "dist_branch",
    ):
        assert f'"{switch}"' in topology
    assert 'net.addSwitch("mpls_cloud", cls=OVSBridge' in topology
