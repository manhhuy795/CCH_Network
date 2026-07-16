from __future__ import annotations

import importlib.util
import json
import socket
import sys
import threading
import types
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"


class _Node:
    def config(self, **_params):
        return None

    def terminate(self):
        return None


class _FakeNet:
    nameToNode: dict[str, object] = {}

    def get(self, name: str):
        raise KeyError(name)


def _load_topology_module(monkeypatch):
    mininet = types.ModuleType("mininet")
    modules = {
        "mininet": mininet,
        "mininet.cli": types.ModuleType("mininet.cli"),
        "mininet.link": types.ModuleType("mininet.link"),
        "mininet.log": types.ModuleType("mininet.log"),
        "mininet.net": types.ModuleType("mininet.net"),
        "mininet.node": types.ModuleType("mininet.node"),
    }
    modules["mininet.cli"].CLI = object
    modules["mininet.link"].TCLink = object
    modules["mininet.log"].info = lambda *_args, **_kwargs: None
    modules["mininet.log"].setLogLevel = lambda *_args, **_kwargs: None
    modules["mininet.net"].Mininet = object
    modules["mininet.node"].Node = _Node
    modules["mininet.node"].OVSBridge = object
    modules["mininet.node"].OVSKernelSwitch = object
    modules["mininet.node"].RemoteController = object
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    module_name = f"topology_transport_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, TOPOLOGY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeConnection:
    def __init__(self, chunks, *, broken_pipe=False):
        self.chunks = list(chunks)
        self.broken_pipe = broken_pipe
        self.sent: list[bytes] = []
        self.closed = False

    def settimeout(self, _timeout):
        return None

    def recv(self, _size):
        return self.chunks.pop(0) if self.chunks else b""

    def sendall(self, payload):
        if self.broken_pipe:
            raise BrokenPipeError("forced test failure")
        self.sent.append(payload)

    def close(self):
        self.closed = True

    def response(self):
        assert self.sent
        return json.loads(self.sent[-1].split(b"\n", 1)[0].decode("utf-8"))


@pytest.fixture
def agent(monkeypatch):
    module = _load_topology_module(monkeypatch)
    return module, module.MininetControlAgent(
        _FakeNet(),
        {"links": [], "hosts": {}},
        Path("unused-test.sock"),
        "test-token",
    )


def _connection_request(token: str, command: str = "HEALTH", request_id: str | None = None):
    payload = {
        "token": token,
        "command": command,
        "request_id": request_id or uuid.uuid4().hex,
    }
    return _FakeConnection([(json.dumps(payload) + "\n").encode("utf-8")])


def _assert_healthy(agent):
    connection = _connection_request("test-token")
    agent._serve_connection(connection)
    response = connection.response()
    assert response["ok"] is True
    assert response["agent_alive"] is True
    assert response["protocol_version"] == 1
    assert response["request_id"]


@pytest.mark.parametrize(
    "raw",
    [
        b"{broken json}\n",
        b"\n",
        json.dumps({"token": "wrong", "command": "HEALTH", "request_id": "wrong-token"}).encode() + b"\n",
    ],
)
def test_invalid_requests_do_not_kill_agent(agent, raw):
    _module, control_agent = agent
    connection = _FakeConnection([raw])
    control_agent._serve_connection(connection)
    assert connection.response()["ok"] is False
    _assert_healthy(control_agent)


def test_disconnects_and_broken_pipe_do_not_kill_agent(agent):
    _module, control_agent = agent
    control_agent._serve_connection(_FakeConnection([b""]))
    control_agent._serve_connection(_connection_request(
        "test-token",
        request_id="disconnect-before-response",
    ))
    broken = _connection_request("test-token", request_id="forced-broken-pipe")
    broken.broken_pipe = True
    control_agent._serve_connection(broken)
    _assert_healthy(control_agent)


def test_fifty_health_requests_and_oversize_request_keep_agent_alive(agent):
    module, control_agent = agent
    for _ in range(50):
        _assert_healthy(control_agent)

    connection = _FakeConnection([b"x" * (module.CONTROL_MAX_REQUEST_BYTES + 1) + b"\n"])
    control_agent._serve_connection(connection)
    response = connection.response()
    assert response["ok"] is False
    assert response["error_code"] == "REQUEST_TOO_LARGE"
    _assert_healthy(control_agent)


def test_stale_socket_cleanup_and_restart(monkeypatch, tmp_path):
    module = _load_topology_module(monkeypatch)
    path = tmp_path / "agent.sock"
    path.touch()
    monkeypatch.setattr(module.stat, "S_ISSOCK", lambda _mode: True)

    class FakeServer:
        def bind(self, address):
            Path(address).touch()

        def listen(self, _backlog):
            return None

        def settimeout(self, _timeout):
            return None

        def accept(self):
            threading.Event().wait(0.005)
            raise module.socket.timeout()

        def shutdown(self, _how):
            return None

        def close(self):
            return None

    monkeypatch.setattr(module.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(module.socket, "socket", lambda *_args, **_kwargs: FakeServer())
    monkeypatch.setattr(module.MininetControlAgent, "_socket_is_active", lambda _self: False)

    agent = module.MininetControlAgent(_FakeNet(), {"links": [], "hosts": {}}, path, "test-token")
    agent.start()
    assert agent.ready.is_set()
    agent.stop()
    assert not path.exists()

    agent.start()
    assert agent.ready.is_set()
    agent.stop()
    assert not path.exists()


def test_active_socket_is_not_removed(agent, tmp_path, monkeypatch):
    module, control_agent = agent
    path = tmp_path / "active.sock"
    path.touch()
    control_agent.socket_path = path
    monkeypatch.setattr(module.stat, "S_ISSOCK", lambda _mode: True)
    monkeypatch.setattr(control_agent, "_socket_is_active", lambda: True)

    with pytest.raises(RuntimeError, match="dang chay"):
        control_agent._remove_stale_socket()
    assert path.exists()
