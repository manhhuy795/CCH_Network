from pathlib import Path

from dashboard.backend.app.live_mininet import topology_payload
from scripts.common import load_vars
from scripts.network_model import build_host_inventory, load_network_model, validate_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine
from sdn_mpls_demo.runtime_contract import RUNTIME_BACKBONE_LINK_MAP, source_truth_runtime_links


ROOT = Path(__file__).resolve().parents[1]


def test_project_c_is_one_vlan_split_evenly_between_sites():
    model = load_network_model()
    hosts = build_host_inventory(model)
    project_c = [host for host in hosts.values() if host["group"] == "project_c"]

    assert len(project_c) == 20
    assert sum(host["site"] == "hq" for host in project_c) == 10
    assert sum(host["site"] == "branch_telesale" for host in project_c) == 10
    assert {host["vlan"] for host in project_c} == {40}
    assert {host["ip"].rsplit(".", 1)[0] for host in project_c} == {"172.16.40"}
    assert validate_network_model(model) == []


def test_vlan40_has_one_centralized_gateway_and_is_not_routed_over_l3vpn():
    model = load_network_model()
    service = model["l2vpn_services"]["vlan40_project_c"]
    routes = load_vars()

    assert service["service_type"] == "vpws"
    assert service["gateway_site"] == "hq"
    assert service["gateway_node"] == "core_hq"
    assert service["runtime_mode"] == "transparent_linux_bridge"
    assert "172.16.40.0/24" not in {
        route["prefix"] for route in routes["routes"]["telesale_l3_gateway"]["user_routes"]
    }
    assert "172.16.40.0/24" not in {
        route["prefix"] for route in routes["ce_telesale"]["mpls_routes"]
    }

    topology_source = (ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py").read_text(encoding="utf-8")
    hq_router_block = topology_source.split("configure_vlan_router_interface(\n        hq_l3", 1)[1].split(")\n    configure_router_interface", 1)[0]
    branch_router_block = topology_source.split("configure_vlan_router_interface(\n        telesale_l3", 1)[1].split(")\n    configure_router_interface", 1)[0]
    assert '(40, "172.16.40.1/24")' in hq_router_block
    assert "172.16.40.1/24" not in branch_router_block


def test_vpws_runtime_has_two_attachment_circuits_and_failure_control_segments():
    model = load_network_model()
    runtime_links = source_truth_runtime_links(model)
    l2vpn_links = [link for link in runtime_links if "l2vpn_vpws40" in link[:2]]

    assert set(RUNTIME_BACKBONE_LINK_MAP) >= {
        frozenset(("dist_hq_2", "l2vpn_vpws40")),
        frozenset(("dist_branch", "l2vpn_vpws40")),
    }
    assert {link[:4] for link in l2vpn_links} == {
        ("dist_hq_2", "l2vpn_vpws40", "d2-eth40", "pw40-hq"),
        ("dist_branch", "l2vpn_vpws40", "bd-eth40", "pw40-br"),
    }
    topology_source = (ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py").read_text(encoding="utf-8")
    assert '"dist_hq_2-l2vpn_vpws40": [("dist_hq_2", "l2vpn40")]' in topology_source
    assert '"dist_branch-l2vpn_vpws40": [("dist_branch", "l2vpn40")]' in topology_source


def test_policy_and_dashboard_expose_the_cross_site_l2_path_and_limitations():
    engine = PolicyEngine(ROOT / "sdn_mpls_demo" / "policy.yml")
    decision = engine.decide("h40_11", "h40_01")
    payload = topology_payload()

    assert decision["action"] == "allow"
    assert decision["path"] == [
        "project_c", "access_branch", "dist_branch", "l2vpn_vpws40",
        "dist_hq_2", "access_floor2", "project_c",
    ]
    assert "core_hq" not in decision["path"]
    assert "VPWS" in decision["reason"]
    assert payload["l2vpn"] == {
        "service": "vlan40_project_c",
        "type": "VPWS / E-Line logic",
        "customer_vlan": 40,
        "sites": ["hq", "telesale"],
        "gateway_site": "hq",
        "gateway_node": "core_hq",
        "runtime_node": "l2vpn_vpws40",
        "runtime_bridge": "l2vpn40",
        "controller_managed": False,
        "simulation_scope": "Transparent Ethernet forwarding; no MPLS labels or PE/P signaling",
    }
    assert "project_c" in next(site["groups"] for site in payload["sites"] if site["id"] == "hq")
    assert "project_c" in next(site["groups"] for site in payload["sites"] if site["id"] == "telesale")
