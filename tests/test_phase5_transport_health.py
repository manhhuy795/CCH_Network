from __future__ import annotations

from dashboard.backend.app import mininet_control, runtime_health


def test_health_does_not_treat_stale_socket_response_as_agent_online(monkeypatch):
    monkeypatch.setattr(
        mininet_control,
        "request_agent",
        lambda *_args, **_kwargs: {
            "ok": True,
            "available": True,
            "agent_alive": False,
        },
    )

    response = mininet_control.health()

    assert response["ok"] is False
    assert response["available"] is False
    assert response["error_code"] == "AGENT_NOT_READY"


def test_system_health_keeps_agent_failure_separate_from_backend_online(monkeypatch):
    snapshot = runtime_health.system_health(
        probe=lambda *_args: (True, 1.0, None),
        agent_health=lambda: {
            "ok": False,
            "available": False,
            "agent_alive": False,
            "error_code": "AGENT_NOT_READY",
            "message": "agent thread stopped",
        },
        live_status=lambda: {"ok": False, "bridges": {}, "user_hosts_online": 0},
        include_flow_inventory=False,
    )

    assert snapshot["components"]["backend"]["status"] == "online"
    assert snapshot["components"]["mininet_control_agent"]["status"] == "offline"
    assert snapshot["components"]["mininet_control_agent"]["error_code"] == "AGENT_NOT_READY"
    assert snapshot["ok"] is False
