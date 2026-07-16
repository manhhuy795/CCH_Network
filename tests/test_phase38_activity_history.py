import json
import time


def test_activity_store_redacts_sensitive_fields(monkeypatch, tmp_path):
    from dashboard.backend.app import activity

    activity_file = tmp_path / "dashboard_activity.jsonl"
    monkeypatch.setattr(activity, "ACTIVITY_FILE", activity_file)
    monkeypatch.setattr(activity, "CONTROLLER_EVENTS_FILE", tmp_path / "controller_events.jsonl")

    activity.append_event(
        component="backend",
        event_type="auth",
        message="Auth event",
        technical_detail={"token": "do-not-store", "nested": {"authorization": "Bearer secret"}},
    )

    raw = activity_file.read_text(encoding="utf-8")
    assert "do-not-store" not in raw
    assert "Bearer secret" not in raw
    assert raw.count("[REDACTED]") == 2


def test_record_operation_keeps_task_timing_and_result(monkeypatch, tmp_path):
    from dashboard.backend.app import activity

    monkeypatch.setattr(activity, "ACTIVITY_FILE", tmp_path / "dashboard_activity.jsonl")
    monkeypatch.setattr(activity, "CONTROLLER_EVENTS_FILE", tmp_path / "controller_events.jsonl")
    started = activity.utc_now()
    result = activity.record_operation(
        user_action="Ping",
        event_type="ping",
        component="mininet_control_agent",
        source="h30_01",
        destination="h90",
        started_at=started,
        started_monotonic=time.monotonic(),
        payload={"ok": True, "message": "Ping thành công", "result": {"rtt_avg_ms": 10}},
    )
    history = activity.activity_payload()

    assert result["task_id"]
    assert result["task_status"] == "success"
    assert result["ended_at"]
    assert result["duration_ms"] >= 0
    assert history["tasks"][0]["user_action"] == "Ping"
    assert history["tasks"][0]["result_summary"] == "Ping thành công"
    assert history["events"][0]["source"] == "h30_01"


def test_activity_api_returns_real_tracked_ping_without_token_leak(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from dashboard.backend.app import activity, api as api_module
    from dashboard.backend.app.main import app

    monkeypatch.setenv("CCH_DASHBOARD_OPERATOR_TOKEN", "phase38-secret")
    monkeypatch.setattr(activity, "ACTIVITY_FILE", tmp_path / "dashboard_activity.jsonl")
    monkeypatch.setattr(activity, "CONTROLLER_EVENTS_FILE", tmp_path / "controller_events.jsonl")
    monkeypatch.setattr(api_module, "run_ping", lambda *_args: {
        "ok": True,
        "message": "Ping runtime PASS",
        "decision": {"action": "allow", "path": ["project_b", "core_hq", "h90"]},
        "result": {"rtt_avg_ms": 8, "packet_loss_percent": 0},
        "raw": "0% packet loss",
    })
    client = TestClient(app)
    headers = {"X-CCH-Operator-Token": "phase38-secret"}

    response = client.post("/api/test/ping", json={"source": "h30_01", "destination": "h90"}, headers=headers)
    history = client.get("/api/activity", headers=headers)

    assert response.status_code == 200
    assert response.json()["task_id"]
    assert history.status_code == 200
    assert history.json()["tasks"][0]["status"] == "success"
    assert history.json()["events"][0]["event_type"] == "ping"
    assert "phase38-secret" not in json.dumps(history.json())
