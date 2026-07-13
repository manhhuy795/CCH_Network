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
    assert len(topology["hosts"]) == 109
    assert topology["summary"]["user_count"] == 104
    assert topology["summary"]["controlled_ovs_count"] == 8
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
    assert "Giám sát Hybrid MPLS L3VPN + SDN Call Center CCH" in html
    assert "Ping thực tế" in html
    assert "Chất lượng cuộc gọi" in html
    assert "Sơ đồ logic và luồng gói tin" in html
    assert "/assets/So_do_logic_CCH.png" not in html
    assert "Bảng luồng OpenFlow dễ đọc" in html
    assert 'id="link-core_hq-fw_hq"' in html
    assert 'id="link-ce_hq-mpls_cloud"' in html
    assert 'id="link-mpls_cloud-ce_branch"' in html
    assert 'id="link-dist_branch-wan"' not in html
    assert 'id="wan"' not in html
    assert "FIREWALL HQ TẠI BIÊN SITE" in html
    assert "FIREWALL BRANCH TẠI BIÊN SITE" in html
    assert "Phòng IT" in html
    assert 'id="link-it_support-access_hq_it"' in html
    assert "BẢO MẬT / INTERNET EDGE" not in html

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
    assert "cách ly" in denied["reason"]
    assert denied["path"] == ["project_a", "access_hq_a", "core_hq"]
    assert denied["blocked_at"] == "core_hq"

    social = policy_decision("h50_01", "hsocial")
    assert social["path"] == ["telesale", "access_branch", "dist_branch", "fw_branch"]
    assert social["blocked_at"] == "fw_branch"

    intersite = policy_decision("h50_01", "h20_01")
    assert intersite["action"] == "allow"
    assert intersite["path"] == [
        "telesale",
        "access_branch",
        "dist_branch",
        "ce_branch",
        "mpls_cloud",
        "ce_hq",
        "core_hq",
        "access_hq_a",
        "project_a",
    ]

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
