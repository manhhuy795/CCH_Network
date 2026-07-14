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
    assert support_social["action"] == "deny"
    assert support_social["blocked_at"] == "core_hq"


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
    assert "khong phai cuoc goi SIP/RTP hoan chinh" in good["estimation_note"]


def test_voice_softphone_wording_is_estimation_not_real_sip_call():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.live_mininet import estimate_voice_quality

    frontend_test_panel = (repo_root / "dashboard" / "frontend" / "src" / "components" / "TestPanel.tsx").read_text(encoding="utf-8")
    metrics_panel = (repo_root / "dashboard" / "frontend" / "src" / "components" / "MetricsPanel.tsx").read_text(encoding="utf-8")
    controller = (repo_root / "sdn_mpls_demo" / "controller_policy.py").read_text(encoding="utf-8")

    live_mininet = (repo_root / "dashboard" / "backend" / "app" / "live_mininet.py").read_text(encoding="utf-8")
    quality = estimate_voice_quality(rtt_ms=40, jitter_ms=4, packet_loss_percent=0)

    assert "khong phai cuoc goi SIP/RTP hoan chinh" in quality["estimation_note"]
    assert "PBX/SBC Voice Service" in live_mininet
    assert "Softphone Cfone/Gphone" in live_mininet
    assert "Uoc luong chat luong thoai" in frontend_test_panel
    assert "MOS/R-factor la uoc luong" in metrics_panel
    assert "QoS dam bao" not in controller


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
    assert "hcall" in CLUSTER_ALLOW_TARGETS["it_support"]
    assert "hsocial" in CLUSTER_DENY_TARGETS["it_support"]
    assert "hinternet" in CLUSTER_DENY_TARGETS["it_support"]


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


def test_policy_toggle_rolls_back_when_controller_admin_is_unavailable():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app import policy as policy_module

    before = policy_module.POLICY_FILE.read_text(encoding="utf-8")
    current = policy_module._load_policy_file()["policies"]["block_social_media"]
    result = policy_module.toggle_policy("block_social_media", not current)
    after = policy_module.POLICY_FILE.read_text(encoding="utf-8")

    assert result["ok"] is False
    assert "rollback" in result["message"].lower()
    assert before == after


def test_controller_admin_reload_reconciles_flows_by_cookie():
    repo_root = Path(__file__).resolve().parents[1]
    controller = (repo_root / "sdn_mpls_demo" / "controller_policy.py").read_text(encoding="utf-8")

    assert "ADMIN_SOCKET" in controller
    assert "ADMIN_TOKEN" in controller
    assert "reload_policy" in controller
    assert "cookie_mask=0xFFFFFFFFFFFFFFFF" in controller
    assert "self._delete_cookie(datapath, cookie)" in controller
    assert "self.install_policy_flows(datapath)" in controller
    assert "self.datapaths[datapath.id] = datapath" in controller


def test_live_link_control_uses_mininet_agent_not_backend_state():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.topology import get_topology

    api_source = (repo_root / "dashboard" / "backend" / "app" / "api.py").read_text(encoding="utf-8")
    main_source = (repo_root / "dashboard" / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    client_source = (repo_root / "dashboard" / "backend" / "app" / "mininet_control.py").read_text(encoding="utf-8")
    topology_source = (repo_root / "sdn_mpls_demo" / "topology_hybrid_sdn.py").read_text(encoding="utf-8")

    assert "app.state.failed_links" not in main_source
    assert "def failed_links" not in api_source
    assert "mininet_control.set_link_state(payload.link_id, \"down\")" in api_source
    assert "mininet_control.set_link_state(payload.link_id, \"up\")" in api_source
    assert "subprocess" not in client_source
    assert "shell=True" not in client_source
    assert "ALLOWED_CONTROL_COMMANDS" in topology_source
    assert "GET_INTERFACE_MAP" in topology_source
    assert "self.net.configLinkStatus(left, right, state)" in topology_source
    assert "MininetControlAgent(net, policy)" in topology_source

    topology = get_topology()
    assert topology["summary"]["live_link_control"] is False
    assert all(link["status"] == "up" for link in topology["links"])


def test_link_fail_endpoint_requires_live_mininet_agent():
    pytest.importorskip("fastapi")
    pytest.importorskip("fastapi.testclient")

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    response = client.post("/api/link/fail", json={"link_id": "core_hq-ce_hq"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is False
    assert payload["available"] is False
    assert payload["failed_links"] == []


def test_backend_decision_schema_is_authoritative_for_animation_metadata():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.live_mininet import enrich_decision, policy_decision

    denied = enrich_decision("h20_01", "h30_01", policy_decision("h20_01", "h30_01"))

    assert denied["action"] == "deny"
    assert denied["path"] == ["project_a", "access_hq_a", "core_hq"]
    assert denied["blocked_at"] == "core_hq"
    assert denied["enforcement_switch"] == "core_hq"
    assert denied["policy"] == "hq_project_isolation"
    assert denied["cookie"] == "0x1001"
    assert denied["priority"] == 400
    assert denied["flow_runtime_available"] is False
    assert denied["metadata_source"] == "policy_engine"

    voice = enrich_decision("h20_01", "h90", policy_decision("h20_01", "h90"))
    assert voice["action"] == "allow"
    assert voice["policy"] == "voice"
    assert voice["cookie"] == "0x1200"
    assert voice["priority"] == 425


def test_ping_result_preserves_backend_packet_path_contract():
    repo_root = Path(__file__).resolve().parents[1]
    live_source = (repo_root / "dashboard" / "backend" / "app" / "live_mininet.py").read_text(encoding="utf-8")
    client_source = (repo_root / "dashboard" / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    panel_source = (repo_root / "dashboard" / "frontend" / "src" / "components" / "TestPanel.tsx").read_text(encoding="utf-8")

    ping_body = live_source.split("def ping(", 1)[1].split("def parse_iperf3", 1)[0]
    assert "mininet_control.first_down_link(decision.get(\"path\", []))" in ping_body
    assert "\"failed_link\": down_link[\"link_id\"]" in ping_body
    assert "decision = enrich_decision(source, destination, decision)" in ping_body
    for field in ("enforcement_switch", "policy", "cookie", "priority", "failed_link"):
        assert field in client_source
    assert "Enforce:" in panel_source
    assert "Failed link:" in panel_source
