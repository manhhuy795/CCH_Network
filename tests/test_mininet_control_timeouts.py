from __future__ import annotations

import json

from dashboard.backend.app import mininet_control


def test_iperf_timeouts_scale_with_duration():
    assert mininet_control.timeout_for_command("RUN_IPERF_CLIENT", {"seconds": 1}) == 11
    assert mininet_control.timeout_for_command("RUN_IPERF_CLIENT", {"seconds": 5}) > 3
    assert mininet_control.timeout_for_command("RUN_IPERF_CLIENT", {"seconds": 10}) > 10


def test_short_commands_keep_short_timeouts():
    assert mininet_control.timeout_for_command("HEALTH") == 3
    assert mininet_control.timeout_for_command("GET_LINK_STATUS") == 3
    assert mininet_control.timeout_for_command("LIVE_STATUS") == 3
    assert mininet_control.timeout_for_command("START_IPERF_SERVER") == 5
    assert mininet_control.timeout_for_command("KILL_PID") == 3
    assert mininet_control.timeout_for_command("DUMP_FLOWS") == 5


def test_ping_timeout_uses_count_and_safety_margin():
    assert mininet_control.timeout_for_command("PING", {"count": 1}) == 4
    assert mininet_control.timeout_for_command("PING", {"count": 10}) == 13
    assert mininet_control.timeout_for_command("PING", {"count": 10, "ping_timeout": 5}) == 45


def test_invalid_duration_and_override_are_bounded():
    assert mininet_control.timeout_for_command("RUN_IPERF_CLIENT", {"seconds": -50}) == 11
    assert mininet_control.timeout_for_command("RUN_IPERF_CLIENT", {"seconds": 999}) == 40
    assert mininet_control._request_timeout("HEALTH", 0, {}) == 1
    assert mininet_control._request_timeout("HEALTH", 999, {}) == 45


def test_timeout_returns_structured_error_and_next_health_passes(monkeypatch, tmp_path):
    socket_marker = tmp_path / "agent.sock"
    socket_marker.touch()
    monkeypatch.setattr(mininet_control, "CONTROL_SOCKET", socket_marker)
    monkeypatch.setattr(mininet_control.socket, "AF_UNIX", 1, raising=False)

    class FakeClient:
        def __init__(self):
            self.command = None
            self.request_id = None
            self.timeout = None
            self.responded = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def settimeout(self, timeout):
            self.timeout = timeout

        def connect(self, _path):
            return None

        def sendall(self, payload):
            request = json.loads(payload.decode("utf-8"))
            self.command = request["command"]
            self.request_id = request["request_id"]

        def recv(self, _size):
            if self.command == "RUN_IPERF_CLIENT":
                raise mininet_control.socket.timeout()
            if self.responded:
                return b""
            self.responded = True
            return (json.dumps({
                "ok": True,
                "agent_alive": True,
                "protocol_version": 1,
                "request_id": self.request_id,
            }) + "\n").encode("utf-8")

    clients: list[FakeClient] = []

    def socket_factory(*_args, **_kwargs):
        client = FakeClient()
        clients.append(client)
        return client

    monkeypatch.setattr(mininet_control.socket, "socket", socket_factory)

    timed_out = mininet_control.request_agent("RUN_IPERF_CLIENT", seconds=5)
    assert timed_out["ok"] is False
    assert timed_out["error_code"] == "AGENT_TIMEOUT"
    assert timed_out["command"] == "RUN_IPERF_CLIENT"
    assert timed_out["timeout_seconds"] == 15
    assert clients[0].timeout == 15

    healthy = mininet_control.health()
    assert healthy["ok"] is True
    assert healthy["agent_alive"] is True
    assert clients[1].timeout == 3
