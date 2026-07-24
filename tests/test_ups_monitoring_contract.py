from pathlib import Path

from scripts.network_model import build_host_inventory, load_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine


def test_ups_are_monitored_endpoints_not_network_devices():
    model = load_network_model()
    hosts = build_host_inventory(model)
    ups = [host for host in hosts.values() if host.get("role") == "ups"]
    assert {host["name"] for host in ups} == {"ups_floor1", "ups_core_1", "ups_core_2", "ups_branch_1"}
    assert not any(name.startswith("ups_") for name in model["switches"])
    assert not any(name.startswith("ups_") for name in model["infrastructure"])


def test_ups_monitoring_uses_real_policy_path_without_ups_as_transit():
    engine = PolicyEngine(Path("sdn_mpls_demo/policy.yml"))
    for source in ("ups_floor1", "ups_core_1", "ups_branch_1"):
        decision = engine.decide(source, "hmonitor")
        assert decision["action"] == "allow"
        assert engine.endpoint(source)["group"] in decision["path"]
        assert "hmonitor" == decision["path"][-1]
        assert "ups_floor1" not in decision["path"][1:]
