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
    assert "hinternet" in CLUSTER_ALLOW_TARGETS["it_support"]
    assert "hsocial" in CLUSTER_DENY_TARGETS["it_support"]
    assert "hinternet" not in CLUSTER_DENY_TARGETS["it_support"]


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
    assert "mininet_control.delete_cookie_flows(switch, cookie, COOKIE_MASK)" in source
    assert "mininet_control.add_manual_drop(switch, cookie, src_ip, dst_ip)" in source
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
    assert '"LINK_DOWN"' in client_source
    assert '"LINK_UP"' in client_source
    assert "return request_agent(command, link_id=link_id)" in client_source

    topology = get_topology()
    assert topology["summary"]["live_link_control"] is False
    assert all(link["status"] == "up" for link in topology["links"])


def test_link_fail_endpoint_requires_live_mininet_agent(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("fastapi.testclient")

    monkeypatch.setenv("CCH_DASHBOARD_OPERATOR_TOKEN", "link-secret")

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    response = client.post(
        "/api/link/fail",
        json={"link_id": "core_hq-ce_hq"},
        headers={"X-CCH-Operator-Token": "link-secret"},
    )
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


def test_realtime_metrics_contract_uses_pair_and_flow_delta():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.live_mininet import pair_realtime_metrics

    live_source = (repo_root / "dashboard" / "backend" / "app" / "live_mininet.py").read_text(encoding="utf-8")
    main_source = (repo_root / "dashboard" / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    realtime_panel = (repo_root / "dashboard" / "frontend" / "src" / "components" / "RealtimePanel.tsx").read_text(encoding="utf-8")
    client_source = (repo_root / "dashboard" / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")

    payload = pair_realtime_metrics("h20_01", "h90", previous_bytes=0, previous_time=1)

    for field in ("source", "destination", "timestamp", "delay_ms", "packet_loss_percent", "jitter_ms", "throughput_mbps", "flow_packets", "flow_bytes", "status"):
        assert field in payload
        assert field in client_source
    assert payload["source"] == "h20_01"
    assert payload["destination"] == "h90"
    assert payload["status"] == "monitoring"

    pair_body = live_source.split("def pair_realtime_metrics", 1)[1].split("def manual_block_cookie", 1)[0]
    assert "delta_bytes = max(0, byte_count - previous_bytes)" in pair_body
    assert "throughput_mbps = round((delta_bytes * 8) / (timestamp - previous_time) / 1_000_000, 4)" in pair_body
    assert "iperf(" not in pair_body
    assert "flow_bytes" in main_source
    assert "setHistory([])" in realtime_panel
    assert "slice(-60)" in realtime_panel
    assert "Math.random" not in realtime_panel


def test_iperf_sessions_are_isolated_and_concurrency_limited():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app import live_mininet

    live_source = (repo_root / "dashboard" / "backend" / "app" / "live_mininet.py").read_text(encoding="utf-8")
    iperf_body = live_source.split("def iperf(", 1)[1].split("def estimate_voice_quality", 1)[0]

    assert "pkill" not in iperf_body
    assert "dashboard_iperf3.log" not in iperf_body
    assert "session_id" in iperf_body
    assert '"port": port' in iperf_body
    assert '"duration": seconds' in iperf_body
    assert "mininet_control.start_iperf_server(destination, port, log_path, session_id)" in iperf_body
    assert "mininet_control.run_iperf_client(" in iperf_body
    assert "mininet_control.kill_pid(destination, server_pid, session_id)" in iperf_body
    assert "_destination_lock(destination)" in iperf_body

    with live_mininet._IPERF_GLOBAL_LOCK:
        live_mininet._IPERF_ACTIVE_SESSIONS.clear()
        live_mininet._IPERF_PORT_CURSOR = 0

    sessions = []
    try:
        for index in range(live_mininet.IPERF_MAX_CONCURRENT):
            registered, session = live_mininet._register_iperf_session(
                f"h20_{index + 1:02d}",
                f"h90_{index + 1:02d}",
                "tcp",
                5,
            )
            assert registered is True
            sessions.append(session)

        registered, rejected = live_mininet._register_iperf_session("h20_99", "h90", "tcp", 5)
        assert registered is False
        assert rejected["ok"] is False
        assert "phien iperf" in rejected["message"]
        assert len({session["port"] for session in sessions}) == live_mininet.IPERF_MAX_CONCURRENT
        assert live_mininet._destination_lock("h90") is live_mininet._destination_lock("h90")
    finally:
        for session in sessions:
            live_mininet._finish_iperf_session(session["session_id"])


def test_frontend_prevents_duplicate_long_running_actions():
    repo_root = Path(__file__).resolve().parents[1]
    app_source = (repo_root / "dashboard" / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "const actionInFlight = useRef(false)" in app_source
    assert "if (actionInFlight.current) return" in app_source
    assert "actionInFlight.current = true" in app_source
    assert "actionInFlight.current = false" in app_source


def test_privileged_mininet_operations_are_split_into_control_agent():
    repo_root = Path(__file__).resolve().parents[1]

    live_source = (repo_root / "dashboard" / "backend" / "app" / "live_mininet.py").read_text(encoding="utf-8")
    control_source = (repo_root / "dashboard" / "backend" / "app" / "mininet_control.py").read_text(encoding="utf-8")
    topology_source = (repo_root / "sdn_mpls_demo" / "topology_hybrid_sdn.py").read_text(encoding="utf-8")

    assert "subprocess" not in live_source
    assert "mnexec" not in live_source.replace('"mnexec": command_exists("mnexec")', "")
    assert "ovs-ofctl" not in live_source
    assert "ovs-vsctl" not in live_source
    assert "shell=True" not in live_source
    assert "raw shell" not in control_source.lower()

    ping_body = live_source.split("def ping(", 1)[1].split("def parse_iperf3", 1)[0]
    flows_body = live_source.split("def ovs_flows(", 1)[1].split("def current_metrics", 1)[0]
    block_body = live_source.split("def temporary_block", 1)[1].split("def live_status", 1)[0]

    assert "mininet_control.ping_detailed(" in ping_body
    assert "mininet_control.dump_flows(switch)" in flows_body
    assert "mininet_control.add_manual_drop" in block_body
    assert "mininet_control.delete_cookie_flows" in block_body

    for command in (
        "PING",
        "START_IPERF_SERVER",
        "RUN_IPERF_CLIENT",
        "KILL_PID",
        "DUMP_FLOWS",
        "OVS_BR_EXISTS",
        "ADD_MANUAL_DROP",
        "DEL_COOKIE_FLOWS",
    ):
        assert f'"{command}"' in topology_source

    assert "command not in ALLOWED_CONTROL_COMMANDS" in topology_source
    assert "re.fullmatch" in topology_source


def test_operator_actions_require_it_token(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("fastapi.testclient")

    monkeypatch.setenv("CCH_DASHBOARD_OPERATOR_TOKEN", "phase18-secret")

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from fastapi.testclient import TestClient
    from app import api as api_module
    from app.main import app

    client = TestClient(app)
    monkeypatch.setattr(api_module, "run_ping", lambda *_args: {
        "ok": True,
        "message": "ping ok",
        "decision": {"action": "allow", "path": []},
        "result": {"reachable": True},
        "raw": "0% packet loss",
    })

    status_response = client.get("/api/auth/status")
    assert status_response.status_code == 200
    assert status_response.json()["operator_token_configured"] is True

    denied = client.post("/api/test/ping", json={"source": "h20_01", "destination": "h90"})
    assert denied.status_code == 401
    assert "IT operator token" in denied.text

    allowed = client.post(
        "/api/test/ping",
        json={"source": "h20_01", "destination": "h90"},
        headers={"X-CCH-Operator-Token": "phase18-secret"},
    )
    assert allowed.status_code == 200

    client_source = (repo_root / "dashboard" / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    app_source = (repo_root / "dashboard" / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    shell_source = (repo_root / "dashboard" / "frontend" / "src" / "components" / "layout" / "AppShell.tsx").read_text(encoding="utf-8")
    start_script = (repo_root / "scripts" / "start_demo.sh").read_text(encoding="utf-8")

    assert "X-CCH-Operator-Token" in client_source
    assert "localStorage" in client_source
    assert "IT operator token" in shell_source
    assert "verifyOperator" in app_source
    assert 'label="Đã xác thực"' in shell_source
    assert "secrets.token_urlsafe" in start_script
    assert "cch-it-demo-token" not in start_script


def test_phase27_security_rejects_bad_tokens_hosts_and_injection(monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("fastapi.testclient")

    monkeypatch.setenv("CCH_DASHBOARD_OPERATOR_TOKEN", "operator-secret")

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    no_token = client.post("/api/live/block", json={"source": "h20_01", "destination": "h90"})
    assert no_token.status_code == 401

    wrong_token = client.post(
        "/api/live/block",
        json={"source": "h20_01", "destination": "h90"},
        headers={"X-CCH-Operator-Token": "user-token"},
    )
    assert wrong_token.status_code == 403

    injection = client.post(
        "/api/test/ping",
        json={"source": "h20_01;touch /tmp/pwned", "destination": "h90"},
        headers={"X-CCH-Operator-Token": "operator-secret"},
    )
    assert injection.status_code == 422

    bad_link = client.post(
        "/api/link/fail",
        json={"link_id": "core_hq-ce_hq;rm -rf /"},
        headers={"X-CCH-Operator-Token": "operator-secret"},
    )
    assert bad_link.status_code == 422

    main_source = (repo_root / "dashboard" / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    models_source = (repo_root / "dashboard" / "backend" / "app" / "models.py").read_text(encoding="utf-8")
    assert 'websocket.query_params.get("source")' in main_source
    assert 'websocket.query_params.get("destination")' in main_source
    assert "SAFE_ID_PATTERN" in models_source
    assert "reject_shell_metacharacters" in models_source


def test_cors_is_restricted_to_dashboard_origins():
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.security import cors_origin_regex, cors_origins

    main_source = (repo_root / "dashboard" / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    security_source = (repo_root / "dashboard" / "backend" / "app" / "security.py").read_text(encoding="utf-8")

    assert 'allow_origins=["*"]' not in main_source
    assert 'allow_headers=["*"]' not in main_source
    assert "allow_credentials=False" in main_source
    assert "X-CCH-Operator-Token" in main_source
    assert cors_origins() == ["http://127.0.0.1:5173", "http://localhost:5173"]
    assert "192\\.168" in cors_origin_regex()
    assert "CCH_DASHBOARD_CORS_ORIGINS" in security_source


def test_dashboard_uses_six_operational_sidebar_destinations():
    repo_root = Path(__file__).resolve().parents[1]
    app_source = (repo_root / "dashboard" / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    shell_source = (repo_root / "dashboard" / "frontend" / "src" / "components" / "layout" / "AppShell.tsx").read_text(encoding="utf-8")
    overview_source = (repo_root / "dashboard" / "frontend" / "src" / "components" / "OverviewPage.tsx").read_text(encoding="utf-8")
    test_panel = (repo_root / "dashboard" / "frontend" / "src" / "components" / "TestPanel.tsx").read_text(encoding="utf-8")
    event_log = (repo_root / "dashboard" / "frontend" / "src" / "components" / "EventLog.tsx").read_text(encoding="utf-8")
    policy_panel = (repo_root / "dashboard" / "frontend" / "src" / "components" / "PolicyPanel.tsx").read_text(encoding="utf-8")

    assert 'DashboardPage = "overview" | "topology" | "testing" | "policy" | "performance" | "events"' in shell_source
    for label in ("Tổng quan", "Topology", "Kiểm tra kết nối", "Chính sách & OpenFlow", "Hiệu năng", "Sự kiện & nhật ký"):
        assert label in shell_source
    for overview_item in ("Controller", "Backend", "Mininet", "Control Agent", "Open vSwitch", "WebSocket", "Host online", "Link/cảnh báo"):
        assert overview_item in overview_source
    for measurement_item in ("Kiem tra Ping", "Throughput TCP", "Jitter UDP", "Uoc luong chat luong thoai"):
        assert measurement_item in test_panel
    assert "animate(payload.decision.path)" in app_source
    assert "TopologyCanvas" in app_source
    assert "Toggle policy ghi policy.yml atomic" in policy_panel
    for log_item in ("Packet-In", "FlowMod", "policy reload", "link down/up", "measurement", "warning", "error"):
        assert log_item in event_log


def test_endpoint_selector_is_searchable_grouped_combobox():
    repo_root = Path(__file__).resolve().parents[1]
    test_panel = (repo_root / "dashboard" / "frontend" / "src" / "components" / "TestPanel.tsx").read_text(encoding="utf-8")
    styles = (repo_root / "dashboard" / "frontend" / "src" / "styles" / "global.css").read_text(encoding="utf-8")

    assert "<select" not in test_panel
    assert "EndpointCombobox" in test_panel
    assert 'role="combobox"' in test_panel
    assert 'role="listbox"' in test_panel
    assert 'role="option"' in test_panel
    for key in ("ArrowDown", "ArrowUp", "Enter", "Escape"):
        assert key in test_panel
    for search_term in ("hostname", "IP", "VLAN", "Project", "site"):
        assert search_term in test_panel
    assert "groupBucket(host)" in test_panel
    assert "HQ - Voice" in test_panel
    assert "Service" in test_panel
    assert " · " in test_panel
    assert ".endpoint-combobox" in styles


def test_topology_uses_grouped_interaction_and_view_controls():
    repo_root = Path(__file__).resolve().parents[1]
    topology_canvas = (repo_root / "dashboard" / "frontend" / "src" / "components" / "TopologyCanvas.tsx").read_text(encoding="utf-8")
    styles = (repo_root / "dashboard" / "frontend" / "src" / "styles" / "global.css").read_text(encoding="utf-8")

    assert "selectedGroup.hosts.slice" in topology_canvas
    assert "chooseEndpoint" in topology_canvas
    assert 'kind: "node"' in topology_canvas
    assert 'kind: "link"' in topology_canvas
    assert "Zoom In" in topology_canvas
    assert "Zoom Out" in topology_canvas
    assert "Fit View" in topology_canvas
    assert "Fullscreen" in topology_canvas
    assert "Reset View" in topology_canvas
    assert "requestFullscreen" in topology_canvas
    assert "style={{ width: `${zoom * 100}%` }}" in topology_canvas
    assert "activeIndex" in topology_canvas
    assert "currentNode === id" in topology_canvas
    assert "prefers-reduced-motion" in styles
    assert ".topology-toolbar" in styles
    assert "h20_01" not in topology_canvas


def test_openflow_control_visualization_is_simplified():
    repo_root = Path(__file__).resolve().parents[1]
    topology_canvas = (repo_root / "dashboard" / "frontend" / "src" / "components" / "TopologyCanvas.tsx").read_text(encoding="utf-8")

    assert "controlledNodes.map" in topology_canvas
    assert 'data-testid="control-path"' in topology_canvas
    assert 'node.type === "switch"' in topology_canvas
    assert "OpenFlow Control Bus" not in topology_canvas
    assert "control-lite" not in topology_canvas
    assert "currentNode === id" in topology_canvas


def test_policy_is_not_rendered_as_topology_node_or_overlay():
    repo_root = Path(__file__).resolve().parents[1]
    topology_canvas = (repo_root / "dashboard" / "frontend" / "src" / "components" / "TopologyCanvas.tsx").read_text(encoding="utf-8")
    styles = (repo_root / "dashboard" / "frontend" / "src" / "styles" / "global.css").read_text(encoding="utf-8")
    policy_panel = (repo_root / "dashboard" / "frontend" / "src" / "components" / "PolicyPanel.tsx").read_text(encoding="utf-8")
    test_panel = (repo_root / "dashboard" / "frontend" / "src" / "components" / "TestPanel.tsx").read_text(encoding="utf-8")

    for forbidden in ("Policy HQ", "Policy Branch", "ping-policy-card", "ping-map"):
        assert forbidden not in topology_canvas
        assert forbidden not in styles
    assert "props.topology?.policy_map" not in topology_canvas
    assert "Chinh sach SDN Edge" in policy_panel
    assert "Policy:" in test_panel
    assert "decision?.reason" in test_panel


def test_readme_documents_automation_and_sdn_runtime_boundaries():
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    for term in ("Network Automation", "YAML", "Jinja2", "Ansible", "generated Cisco/firewall config", "backup/deploy/verify"):
        assert term in readme
    for term in ("SDN runtime", "Mininet", "Open vSwitch", "OS-Ken", "OpenFlow 1.3"):
        assert term in readme
    assert "vars/network_model.yml" in readme
    assert "generated Cisco config khong duoc load vao OVS" in readme
    assert "khong dung de dung Mininet" in readme


def test_legacy_sdn_demo_is_clearly_marked():
    repo_root = Path(__file__).resolve().parents[1]
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    legacy = (repo_root / "sdn_demo" / "LEGACY_README.md").read_text(encoding="utf-8")
    sdn_demo_readme = (repo_root / "sdn_demo" / "README.md").read_text(encoding="utf-8")

    assert "Demo chinh thuc dung cho bao ve" in readme
    assert "`sdn_mpls_demo/`" in readme
    assert "`sdn_demo/` la demo legacy" in readme
    assert "Khong dung `sdn_demo/` trong buoi bao ve chinh" in legacy
    assert "sdn_mpls_demo/" in legacy
    assert "legacy" in sdn_demo_readme.lower()
