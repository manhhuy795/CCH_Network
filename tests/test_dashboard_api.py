import sys
from pathlib import Path

import pytest


def test_dashboard_api_topology_and_policy_endpoints():
    pytest.importorskip("fastapi")

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.policy import get_policy_payload
    from app.topology import get_topology

    topology = get_topology()
    policies = get_policy_payload()

    assert topology["nodes"]
    assert topology["links"]
    assert len(topology["hosts"]) == 115
    assert topology["summary"]["user_count"] == 110
    assert topology["summary"]["controlled_ovs_count"] == 8
    mpls_node = next(node for node in topology["nodes"] if node["id"] == "mpls_cloud")
    assert mpls_node["label"] == "MPLS L3VPN Logic Cloud"
    assert "WAN transport" in mpls_node["subtitle"]
    assert policies["policies"]["block_social_media"] is True


def test_dashboard_serves_live_web_page():
    pytest.importorskip("fastapi")
    pytest.importorskip("fastapi.testclient")

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    response = client.get("/")
    html = response.text

    assert response.status_code == 200
    assert "Hybrid MPLS L3VPN + SDN Edge Policy Demo" in html
    assert "React Dashboard" in html
    assert "/api/topology" in html
    assert "voice_mgmt" not in html

    topology = client.get("/api/topology")
    assert topology.status_code == 200


def test_dashboard_policy_decision_explains_allow_and_deny():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.live_mininet import policy_decision

    assert policy_decision("h20_01", "h90")["action"] == "allow"

    denied = policy_decision("h20_01", "h30_01")
    assert denied["action"] == "deny"
    assert "cach ly" in denied["reason"]
    assert denied["path"] == ["project_a", "access_hq_a", "core_hq"]
    assert denied["blocked_at"] == "core_hq"

    social = policy_decision("h50_01", "hsocial")
    assert social["path"] == ["telesale", "access_branch", "dist_branch"]
    assert social["blocked_at"] == "dist_branch"

    intersite = policy_decision("h50_01", "h20_01")
    assert intersite["action"] == "deny"
    assert intersite["blocked_at"] == "dist_branch"

    support = policy_decision("h70_01", "h20_01")
    assert support["action"] == "allow"
    assert support["path"] == ["it_support", "access_hq_it", "core_hq", "access_hq_a", "project_a"]
    assert "IT" in support["reason"]

    support_branch = policy_decision("h70_01", "h50_01")
    assert support_branch["action"] == "allow"
    assert "mpls_cloud" in support_branch["path"]

    support_social = policy_decision("h70_01", "hsocial")
    assert support_social["action"] == "allow"


def test_call_quality_score_uses_call_center_thresholds():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.live_mininet import estimate_voice_quality

    good = estimate_voice_quality(rtt_ms=40, jitter_ms=4, packet_loss_percent=0)
    bad = estimate_voice_quality(rtt_ms=260, jitter_ms=45, packet_loss_percent=5)

    assert good["passed"] is True
    assert good["mos"] >= 4.0
    assert good["thresholds"]["rtt_ms"] == 150
    assert bad["passed"] is False
    assert bad["mos"] < good["mos"]


def test_cluster_detail_configuration_covers_main_groups():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.live_mininet import CLUSTER_ALLOW_TARGETS, CLUSTER_DENY_TARGETS, CLUSTER_SOURCES

    assert CLUSTER_SOURCES["project_a"][0] == "h20_01"
    assert CLUSTER_SOURCES["telesale"][0] == "h50_01"
    assert "h90" in CLUSTER_ALLOW_TARGETS["project_a"]
    assert "hcall" in CLUSTER_ALLOW_TARGETS["telesale"]
    assert "h50_01" not in CLUSTER_ALLOW_TARGETS["project_a"]
    assert "h20_01" not in CLUSTER_ALLOW_TARGETS["telesale"]
    assert "h30_01" in CLUSTER_DENY_TARGETS["project_a"]
    assert "h50_01" in CLUSTER_DENY_TARGETS["project_a"]
    assert "h20_01" in CLUSTER_DENY_TARGETS["telesale"]
    assert CLUSTER_DENY_TARGETS["it_support"] == ()


def test_manual_block_uses_cookie_and_single_enforcement_switch():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.live_mininet import manual_block_cookie, manual_enforcement_switch, parse_flow_line

    assert manual_enforcement_switch("h20_01", "h30_01") == "core_hq"
    assert manual_enforcement_switch("h50_01", "h60_01") == "dist_branch"
    assert manual_enforcement_switch("h70_01", "h50_01") == "core_hq"
    assert manual_block_cookie("h20_01", "h30_01") == manual_block_cookie("h30_01", "h20_01")

    flow = parse_flow_line(
        "cookie=0x1001, duration=1.0s, priority=400,ip,nw_src=172.16.20.0,nw_dst=172.16.30.0 actions=drop",
        "core_hq",
    )
    assert flow["cookie"] == "0x1001"

    source = (repo_root / "dashboard" / "backend" / "app" / "live_mininet.py").read_text(encoding="utf-8")
    assert 'del-flows", switch, f"cookie=0x{cookie:x}/{COOKIE_MASK}"' in source
    assert 'del-flows", switch, match' not in source
    assert "for switch in CONTROLLED_SWITCHES:" not in source.split("def temporary_block", 1)[1].split("def live_status", 1)[0]
