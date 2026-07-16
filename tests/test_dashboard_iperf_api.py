from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app import live_mininet
from app.models import IperfRequest


TCP_OUTPUT = json.dumps({
    "end": {"sum_received": {"bits_per_second": 40_000_000, "bytes": 5_000_000}},
})
UDP_OUTPUT = json.dumps({
    "end": {
        "sum": {
            "bits_per_second": 18_000_000,
            "bytes": 2_250_000,
            "jitter_ms": 2.2,
            "lost_percent": 0.25,
            "lost_packets": 1,
        },
    },
})


def _reset_sessions():
    with live_mininet._IPERF_GLOBAL_LOCK:
        live_mininet._IPERF_ACTIVE_SESSIONS.clear()
        live_mininet._IPERF_DESTINATION_LOCKS.clear()
        live_mininet._IPERF_PORT_CURSOR = 0


def _install_agent_fakes(monkeypatch, output):
    killed = []

    def start(destination, port, log_path, session_id):
        return {
            "ok": True,
            "listening": True,
            "pid": str(port + 1000),
            "session_id": session_id,
            "host": destination,
            "port": port,
            "log_path": log_path,
            "raw": f"{port + 1000} 1",
        }

    def run(source, destination_ip, port, protocol, seconds, session_id):
        result = live_mininet.parse_iperf3(output)
        return {
            "ok": True,
            "session_id": session_id,
            "protocol": protocol,
            "duration": seconds,
            "result": result,
            "raw": output,
        }

    def kill(host, pid, session_id):
        killed.append((host, pid, session_id))
        return {"ok": True}

    monkeypatch.setattr(live_mininet.mininet_control, "start_iperf_server", start)
    monkeypatch.setattr(live_mininet.mininet_control, "run_iperf_client", run)
    monkeypatch.setattr(live_mininet.mininet_control, "kill_pid", kill)
    return killed


def test_api_duration_is_limited_to_thirty_seconds():
    request = IperfRequest(source="h30_01", destination="h90", protocol="udp", seconds=30)
    assert request.seconds == 30
    with pytest.raises(ValidationError):
        IperfRequest(source="h30_01", destination="h90", protocol="udp", seconds=31)


def test_policy_deny_happens_before_server_start(monkeypatch):
    _reset_sessions()
    starts = []
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "start_iperf_server",
        lambda *_args: starts.append(_args),
    )

    response = live_mininet.iperf("h20_01", "hsocial", "udp", 5)
    assert response["ok"] is False
    assert response["decision"]["action"] == "deny"
    assert starts == []


def test_tcp_udp_results_and_cleanup(monkeypatch):
    for protocol, output in (("tcp", TCP_OUTPUT), ("udp", UDP_OUTPUT)):
        _reset_sessions()
        killed = _install_agent_fakes(monkeypatch, output)
        response = live_mininet.iperf("h30_01", "h90", protocol, 5)

        assert response["ok"] is True
        assert response["result"]["throughput_mbps"] > 0
        assert response["result"]["transferred_bytes"] > 0
        if protocol == "udp":
            assert response["result"]["jitter_ms"] == 2.2
            assert response["result"]["packet_loss_percent"] == 0.25
        assert len(killed) == 1
        assert killed[0][2] == response["session_id"]
        assert live_mininet._IPERF_ACTIVE_SESSIONS == {}
        assert not live_mininet._destination_lock("h90").locked()


@pytest.mark.parametrize(
    ("source", "destination", "protocol"),
    [
        ("h30_01", "h90", "udp"),
        ("h30_01", "h90", "tcp"),
        ("h20_01", "hcall", "udp"),
        ("h50_01", "h90", "udp"),
    ],
)
def test_required_iperf_regression_pairs(monkeypatch, source, destination, protocol):
    _reset_sessions()
    output = UDP_OUTPUT if protocol == "udp" else TCP_OUTPUT
    _install_agent_fakes(monkeypatch, output)
    response = live_mininet.iperf(source, destination, protocol, 5)
    assert response["ok"] is True
    assert response["source"] == source
    assert response["destination"] == destination
    assert response["duration"] == 5


def test_three_udp_runs_remain_healthy_and_use_distinct_sessions(monkeypatch):
    _reset_sessions()
    killed = _install_agent_fakes(monkeypatch, UDP_OUTPUT)
    ping_calls = []
    health_calls = []
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "ping",
        lambda source, destination_ip, count: ping_calls.append((source, destination_ip, count)) or (True, "0% packet loss"),
    )
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "health",
        lambda: health_calls.append(True) or {"ok": True, "agent_alive": True},
    )
    sessions = []
    for _ in range(3):
        sessions.append(live_mininet.iperf("h30_01", "h90", "udp", 5)["session_id"])
        assert live_mininet.mininet_control.ping("h30_01", "172.16.90.10", 1)[0] is True
        assert live_mininet.mininet_control.health()["ok"] is True
    assert len(set(sessions)) == 3
    assert len(killed) == 3
    assert len(ping_calls) == 3
    assert len(health_calls) == 3
    assert live_mininet._IPERF_ACTIVE_SESSIONS == {}


def test_same_destination_returns_structured_busy(monkeypatch):
    _reset_sessions()
    entered = threading.Event()
    release = threading.Event()
    killed = []

    def start(destination, port, log_path, session_id):
        return {
            "ok": True,
            "listening": True,
            "pid": "4242",
            "session_id": session_id,
            "host": destination,
            "port": port,
            "log_path": log_path,
        }

    def run(*_args):
        entered.set()
        release.wait(timeout=2)
        return {"ok": True, "result": live_mininet.parse_iperf3(UDP_OUTPUT), "raw": UDP_OUTPUT}

    monkeypatch.setattr(live_mininet.mininet_control, "start_iperf_server", start)
    monkeypatch.setattr(live_mininet.mininet_control, "run_iperf_client", run)
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "kill_pid",
        lambda host, pid, session_id: killed.append((host, pid, session_id)) or {"ok": True},
    )

    first_result = {}
    worker = threading.Thread(
        target=lambda: first_result.update(live_mininet.iperf("h30_01", "h90", "udp", 5)),
    )
    worker.start()
    assert entered.wait(timeout=2)
    second = live_mininet.iperf("h20_01", "h90", "udp", 5)
    release.set()
    worker.join(timeout=2)

    assert second["ok"] is False
    assert second["error_code"] == "IPERF_DESTINATION_BUSY"
    assert first_result["ok"] is True
    assert len(killed) == 1


def test_different_destinations_use_distinct_ports_concurrently(monkeypatch):
    _reset_sessions()
    barrier = threading.Barrier(2)
    ports = []

    def start(destination, port, log_path, session_id):
        ports.append(port)
        return {
            "ok": True,
            "listening": True,
            "pid": str(port + 1000),
            "session_id": session_id,
            "host": destination,
            "port": port,
            "log_path": log_path,
        }

    def run(*_args):
        barrier.wait(timeout=2)
        return {"ok": True, "result": live_mininet.parse_iperf3(UDP_OUTPUT), "raw": UDP_OUTPUT}

    monkeypatch.setattr(live_mininet.mininet_control, "start_iperf_server", start)
    monkeypatch.setattr(live_mininet.mininet_control, "run_iperf_client", run)
    monkeypatch.setattr(live_mininet.mininet_control, "kill_pid", lambda *_args: {"ok": True})

    results = []
    threads = [
        threading.Thread(target=lambda pair=pair: results.append(live_mininet.iperf(*pair, "udp", 5)))
        for pair in (("h30_01", "h90"), ("h20_01", "hcall"))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert len(results) == 2
    assert all(result["ok"] for result in results)
    assert len(set(ports)) == 2


def test_parse_error_still_cleans_session_and_lock(monkeypatch):
    _reset_sessions()
    killed = []
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "start_iperf_server",
        lambda destination, port, log_path, session_id: {
            "ok": True,
            "listening": True,
            "pid": "4242",
            "session_id": session_id,
        },
    )
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "run_iperf_client",
        lambda *_args: {
            "ok": False,
            "error_code": "IPERF_JSON_INVALID",
            "parse_warning": "invalid json",
            "raw": "not-json",
        },
    )
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "kill_pid",
        lambda host, pid, session_id: killed.append((host, pid, session_id)) or {"ok": True},
    )

    response = live_mininet.iperf("h30_01", "h90", "udp", 5)
    assert response["ok"] is False
    assert response["parse_warning"]
    assert response["raw"] == "not-json"
    assert len(killed) == 1
    assert live_mininet._IPERF_ACTIVE_SESSIONS == {}
    assert not live_mininet._destination_lock("h90").locked()


def test_cleanup_registry_and_lock_even_if_kill_request_raises(monkeypatch):
    _reset_sessions()
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "start_iperf_server",
        lambda destination, port, log_path, session_id: {
            "ok": True,
            "listening": True,
            "pid": "4242",
            "session_id": session_id,
        },
    )
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "run_iperf_client",
        lambda *_args: {"ok": True, "result": live_mininet.parse_iperf3(UDP_OUTPUT), "raw": UDP_OUTPUT},
    )
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "kill_pid",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("kill transport failed")),
    )

    response = live_mininet.iperf("h30_01", "h90", "udp", 5)
    assert response["cleanup_warning"] == "Cleanup iperf gap loi: kill transport failed"
    assert live_mininet._IPERF_ACTIVE_SESSIONS == {}
    assert not live_mininet._destination_lock("h90").locked()
