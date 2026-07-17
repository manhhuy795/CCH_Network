from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app import api, mininet_control, runtime_health


def online_probe(_host, _port, _timeout):
    return True, 1.5, None


def offline_controller_probe(_host, port, _timeout):
    return (False, None, "refused") if port == 6653 else (True, 1.0, None)


def healthy_runtime():
    return {
        "ok": True,
        "agent_alive": True,
        "ovs_bridge": True,
        "bridges": {"core_hq": True, "dist_branch": True},
        "user_hosts_online": 110,
        "mnexec": True,
    }


def test_backend_online_but_agent_offline_is_not_healthy(monkeypatch):
    snapshot = runtime_health.system_health(
        probe=online_probe,
        agent_health=lambda: {
            "ok": False,
            "error_code": "MININET_NOT_RUNNING",
            "message": "socket missing",
        },
        live_status=healthy_runtime,
        include_flow_inventory=False,
    )
    assert snapshot["ok"] is False
    assert snapshot["components"]["backend"]["status"] == "online"
    assert snapshot["components"]["mininet_control_agent"]["status"] == "offline"
    assert snapshot["components"]["mininet_control_agent"]["error_code"] == "MININET_NOT_RUNNING"


def test_agent_timeout_and_controller_offline_are_separate_components():
    snapshot = runtime_health.system_health(
        probe=offline_controller_probe,
        agent_health=lambda: {
            "ok": False,
            "error_code": "AGENT_TIMEOUT",
            "message": "timeout",
        },
        include_flow_inventory=False,
    )
    assert snapshot["components"]["controller"]["error_code"] == "CONTROLLER_OFFLINE"
    assert snapshot["components"]["mininet_control_agent"]["status"] == "degraded"
    assert snapshot["components"]["mininet_control_agent"]["error_code"] == "AGENT_TIMEOUT"


def test_ovs_unavailable_is_reported_without_backend_crash():
    snapshot = runtime_health.system_health(
        probe=online_probe,
        agent_health=lambda: {"ok": True, "agent_alive": True},
        live_status=lambda: {
            "ok": True,
            "ovs_bridge": False,
            "bridges": {"core_hq": False, "dist_branch": False},
            "user_hosts_online": 110,
            "mnexec": True,
        },
        include_flow_inventory=False,
    )
    assert snapshot["components"]["openvswitch"]["status"] == "offline"
    assert snapshot["components"]["openvswitch"]["error_code"] == "OVS_UNAVAILABLE"


def test_stale_socket_maps_to_agent_disconnected(monkeypatch, tmp_path):
    marker = tmp_path / "stale.sock"
    marker.touch()
    monkeypatch.setattr(mininet_control, "CONTROL_SOCKET", marker)
    monkeypatch.setattr(mininet_control.socket, "AF_UNIX", 1, raising=False)

    class RefusedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def settimeout(self, _timeout):
            return None

        def connect(self, _path):
            raise ConnectionRefusedError("stale socket")

    monkeypatch.setattr(mininet_control.socket, "socket", lambda *_args: RefusedSocket())
    response = mininet_control.health()
    assert response["ok"] is False
    assert response["error_code"] == "AGENT_DISCONNECTED"


def test_operation_error_mapping_is_stable():
    assert api._normalize_operation_error({
        "ok": False,
        "error_code": "IPERF_DESTINATION_BUSY",
        "message": "busy",
    })["error_code"] == "IPERF_BUSY"
    assert api._normalize_operation_error({
        "ok": False,
        "error_code": "IPERF_JSON_INVALID",
        "message": "parse",
    })["error_code"] == "IPERF_PARSE_FAILED"
    assert api._normalize_operation_error({
        "ok": False,
        "decision": {"action": "deny"},
        "message": "policy",
    })["error_code"] == "POLICY_DENIED"
    assert api._normalize_operation_error({
        "ok": False,
        "error_code": "AGENT_DISCONNECTED",
        "decision": {"action": "deny"},
        "message": "agent down",
    })["error_code"] == "AGENT_DISCONNECTED"


def test_completed_voice_measurement_is_http_success_even_when_quality_is_poor():
    response = api.operation_response({
        "ok": False,
        "measurement_completed": True,
        "message": "Chat luong chua dat nguong.",
        "result": {"mos": 3.2},
    })
    assert isinstance(response, dict)
    assert response["measurement_completed"] is True


def test_auth_error_codes_and_http_status(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("CCH_DASHBOARD_OPERATOR_TOKEN", "health-secret")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    missing = client.post("/api/test/ping", json={"source": "h20_01", "destination": "h90"})
    wrong = client.post(
        "/api/test/ping",
        json={"source": "h20_01", "destination": "h90"},
        headers={"X-CCH-Operator-Token": "wrong"},
    )
    assert missing.status_code == 401
    assert missing.json()["error_code"] == "AUTH_REQUIRED"
    assert wrong.status_code == 403
    assert wrong.json()["error_code"] == "AUTH_INVALID"
    assert missing.headers["X-Request-ID"]


def test_busy_timeout_and_parse_fail_use_expected_http_status(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("CCH_DASHBOARD_OPERATOR_TOKEN", "health-secret")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    headers = {"X-CCH-Operator-Token": "health-secret"}

    monkeypatch.setattr(api, "run_iperf", lambda *_args: {
        "ok": False,
        "error_code": "IPERF_DESTINATION_BUSY",
        "message": "busy",
    })
    busy = client.post("/api/test/iperf", json={
        "source": "h30_01", "destination": "h90", "protocol": "udp", "seconds": 5,
    }, headers=headers)
    assert busy.status_code == 409
    assert busy.json()["error_code"] == "IPERF_BUSY"

    monkeypatch.setattr(api, "run_iperf", lambda *_args: {
        "ok": False,
        "error_code": "AGENT_TIMEOUT",
        "message": "timeout",
    })
    timeout = client.post("/api/test/iperf", json={
        "source": "h30_01", "destination": "h90", "protocol": "udp", "seconds": 5,
    }, headers=headers)
    assert timeout.status_code == 504

    monkeypatch.setattr(api, "run_iperf", lambda *_args: {
        "ok": False,
        "error_code": "IPERF_JSON_INVALID",
        "message": "parse",
    })
    parse = client.post("/api/test/iperf", json={
        "source": "h30_01", "destination": "h90", "protocol": "udp", "seconds": 5,
    }, headers=headers)
    assert parse.status_code == 502
    assert parse.json()["error_code"] == "IPERF_PARSE_FAILED"


def test_policy_deny_is_200_but_agent_unavailable_is_503(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("CCH_DASHBOARD_OPERATOR_TOKEN", "health-secret")
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    headers = {"X-CCH-Operator-Token": "health-secret"}
    monkeypatch.setattr(api, "run_ping", lambda *_args: {
        "ok": False,
        "error_code": "POLICY_DENIED",
        "message": "policy deny",
        "decision": {"action": "deny", "path": ["h20_01", "core_hq"]},
    })
    denied = client.post(
        "/api/test/ping",
        json={"source": "h20_01", "destination": "h30_01"},
        headers=headers,
    )
    assert denied.status_code == 200
    assert denied.json()["error_code"] == "POLICY_DENIED"

    monkeypatch.setattr(api, "run_ping", lambda *_args: {
        "ok": False,
        "error_code": "AGENT_DISCONNECTED",
        "message": "agent down",
        "decision": {"action": "deny", "path": []},
    })
    unavailable = client.post(
        "/api/test/ping",
        json={"source": "h20_01", "destination": "h30_01"},
        headers=headers,
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error_code"] == "AGENT_DISCONNECTED"


def test_health_and_live_status_expose_all_components(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient
    from app.main import app

    components = {
        name: {
            "status": "online",
            "message_vi": name,
            "checked_at": "2026-01-01T00:00:00+00:00",
            "latency_ms": 1,
            "error_code": None,
            "technical_detail": None,
        }
        for name in (
            "frontend",
            "backend",
            "controller",
            "mininet_topology",
            "mininet_control_agent",
            "openvswitch",
            "websocket",
            "flow_inventory",
        )
    }
    payload = {
        "ok": True,
        "status": "online",
        "message_vi": "ok",
        "checked_at": "2026-01-01T00:00:00+00:00",
        "components": components,
        "runtime": {},
    }
    monkeypatch.setattr(api, "system_health", lambda: payload)
    monkeypatch.setattr(api, "live_health_payload", lambda: {**payload, "available": True})
    client = TestClient(app)

    health = client.get("/api/health")
    live = client.get("/api/live/status")
    assert health.status_code == 200
    assert live.status_code == 200
    for response in (health, live):
        for name, item in response.json()["components"].items():
            assert name in components
            for field in ("status", "message_vi", "checked_at", "latency_ms", "error_code", "technical_detail"):
                assert field in item


def test_start_and_health_scripts_use_component_checks():
    start_script = (REPO_ROOT / "scripts" / "start_demo.sh").read_text(encoding="utf-8")
    health_script = (REPO_ROOT / "scripts" / "check_demo_health.sh").read_text(encoding="utf-8")
    assert "/api/health" in start_script
    assert "pid_alive" in start_script
    assert "stable" in start_script
    assert "tail -n 80" in start_script
    assert "cleanup_failed_start" in start_script
    assert "PID file stale" in start_script
    assert 'port_open 6653' in start_script
    assert 'port_open 5173' in start_script
    assert "prepare_backend_privileges" in start_script
    assert "sudo -v" in start_script
    assert "sudo -n -E" in start_script
    assert "sudo -n" in health_script
    assert "mininet_control_agent" in health_script or "components" in health_script
    assert 'exit "$FAILED"' in health_script


def test_unhandled_exception_hides_traceback_but_logs_request_id(monkeypatch, caplog):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient
    from app.main import app

    @app.get("/api/test-phase32-crash")
    def crash_route():
        raise RuntimeError("phase32-sensitive-trace")

    caplog.set_level(logging.ERROR)
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/test-phase32-crash", headers={"X-Request-ID": "phase32-request"})
    body = response.json()
    assert response.status_code == 500
    assert body["error_code"] == "INTERNAL_ERROR"
    assert body["request_id"] == "phase32-request"
    assert "phase32-sensitive-trace" not in json.dumps(body)
    assert "phase32-sensitive-trace" in caplog.text
    assert "phase32-request" in caplog.text
