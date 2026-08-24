from pathlib import Path

from scripts.common import load_vars
from scripts.generate_configs import generate_configs
from scripts.network_model import load_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine


POLICY = Path("sdn_mpls_demo/policy.yml")


def test_dhcp_is_centralized_and_relayed_at_l3(tmp_path: Path):
    model = load_network_model()
    config = load_vars()
    relay = config["dhcp_relay"]

    assert model["infrastructure_services"]["hdhcp"]["ip"] == "10.10.100.10"
    assert model["infrastructure_services"]["hdhcp"]["switch"] == "infra_access"
    assert relay["server_ip"] == "10.10.100.10"
    assert set(relay["hq_vlans"]) == {93, 101, 103, 104, 110, 120, 140}
    assert relay["branch_vlans"] == [50]

    generate_configs(tmp_path)
    hq = (tmp_path / "hq-core-dist.cfg").read_text(encoding="utf-8")
    branch = (tmp_path / "br-core-dist.cfg").read_text(encoding="utf-8")
    assert hq.count("ip helper-address 10.10.100.10") == len(relay["hq_vlans"])
    assert "interface Vlan93" in hq
    assert "interface Vlan93" not in branch
    assert "interface Vlan50" in branch
    assert "ip helper-address 10.10.100.10" in branch


def test_guest_and_iot_can_reach_only_declared_bootstrap_services():
    engine = PolicyEngine(POLICY)
    assert engine.decide("guest_01", "hdhcp")["action"] == "allow"
    assert engine.decide("guest_01", "hdns")["action"] == "allow"
    assert engine.decide("guest_01", "h101_01")["action"] == "deny"
    assert engine.decide("iot_cam_01", "hdhcp")["action"] == "allow"
    assert engine.decide("iot_cam_01", "h90")["action"] == "deny"
    assert engine.decide("iot_branch_cam_01", "hmonitor")["action"] == "allow"
