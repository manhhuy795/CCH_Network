from __future__ import annotations

import importlib.util
import json
import sys
import threading
import types
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_PATH = REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py"


class _Node:
    def config(self, **_params):
        return None

    def terminate(self):
        return None


class FakeHost:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.commands: list[str] = []

    def cmd(self, command):
        self.commands.append(command)
        return self.responses.pop(0) if self.responses else ""


class FakeNet:
    def __init__(self, hosts):
        self.hosts = hosts
        self.nameToNode = dict(hosts)

    def get(self, name):
        if name not in self.hosts:
            raise KeyError(name)
        return self.hosts[name]


def load_topology_module(monkeypatch):
    modules = {
        "mininet": types.ModuleType("mininet"),
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

    spec = importlib.util.spec_from_file_location(f"iperf_agent_{uuid.uuid4().hex}", TOPOLOGY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def start_request(session_id="abcdef123456", destination="h90", port=5201):
    return {
        "session_id": session_id,
        "destination": destination,
        "port": port,
        "log_path": f"/tmp/cch_iperf/{session_id}.json",
    }


def test_server_requires_listen_and_tracks_pid_ownership(monkeypatch):
    module = load_topology_module(monkeypatch)
    destination = FakeHost(["4242 1\n", ""])
    agent = module.MininetControlAgent(FakeNet({"h90": destination}), {})

    started = agent._start_iperf_server(start_request())
    assert started["ok"] is True
    assert started["listening"] is True
    assert started["pid"] == "4242"
    assert agent.iperf_sessions["abcdef123456"]["host"] == "h90"

    wrong = agent._kill_pid({"session_id": "abcdef123456", "host": "h90", "pid": "9999"})
    assert wrong["ok"] is False
    assert wrong["error_code"] == "IPERF_SESSION_OWNERSHIP_MISMATCH"

    stopped = agent._kill_pid({"session_id": "abcdef123456", "host": "h90", "pid": "4242"})
    assert stopped["ok"] is True
    assert "abcdef123456" not in agent.iperf_sessions


def test_server_not_listening_is_failed_and_cleaned(monkeypatch):
    module = load_topology_module(monkeypatch)
    destination = FakeHost(["4242 0\n", ""])
    agent = module.MininetControlAgent(FakeNet({"h90": destination}), {})

    response = agent._start_iperf_server(start_request())
    assert response["ok"] is False
    assert response["error_code"] == "IPERF_SERVER_NOT_LISTENING"
    assert not agent.iperf_sessions
    assert any("kill -TERM 4242" in command for command in destination.commands)


def test_tcp_and_udp_results_include_runtime_metrics(monkeypatch):
    module = load_topology_module(monkeypatch)
    tcp_output = json.dumps({
        "end": {"sum_received": {"bits_per_second": 50_000_000, "bytes": 6_250_000}},
    })
    udp_output = json.dumps({
        "end": {
            "sum": {
                "bits_per_second": 19_000_000,
                "bytes": 2_375_000,
                "jitter_ms": 1.25,
                "lost_percent": 0.5,
                "lost_packets": 2,
                "packets": 400,
            },
        },
    })
    source = FakeHost([tcp_output, udp_output])
    destination = FakeHost([])
    agent = module.MininetControlAgent(FakeNet({"h30_01": source, "h90": destination}), {})

    for session_id, protocol, port in (
        ("abcdef123456", "tcp", 5201),
        ("abcdef123457", "udp", 5202),
    ):
        agent.iperf_sessions[session_id] = {
            "session_id": session_id,
            "host": "h90",
            "port": port,
            "pid": str(port),
        }
        response = agent._run_iperf_client({
            "session_id": session_id,
            "source": "h30_01",
            "destination_ip": "172.16.90.10",
            "port": port,
            "protocol": protocol,
            "seconds": 5,
        })
        assert response["ok"] is True
        assert response["result"]["throughput_mbps"] > 0
        assert response["result"]["transferred_bytes"] > 0
        if protocol == "udp":
            assert response["result"]["jitter_ms"] == 1.25
            assert response["result"]["packet_loss_percent"] == 0.5
            assert response["result"]["lost_packets"] == 2
            assert response["result"]["total_datagrams"] == 400


def test_missing_json_fields_returns_parse_warning(monkeypatch):
    module = load_topology_module(monkeypatch)
    source = FakeHost([json.dumps({"end": {"sum": {}}})])
    agent = module.MininetControlAgent(FakeNet({"h20_01": source, "hcall": FakeHost()}), {})
    agent.iperf_sessions["abcdef123456"] = {
        "session_id": "abcdef123456",
        "host": "hcall",
        "port": 5201,
        "pid": "4242",
    }

    response = agent._run_iperf_client({
        "session_id": "abcdef123456",
        "source": "h20_01",
        "destination_ip": "198.51.100.20",
        "port": 5201,
        "protocol": "udp",
        "seconds": 5,
    })
    assert response["ok"] is True
    assert response["parse_warning"]
    assert response["raw"]


def test_non_object_json_returns_parse_warning(monkeypatch):
    module = load_topology_module(monkeypatch)
    source = FakeHost(["[]"])
    agent = module.MininetControlAgent(FakeNet({"h20_01": source, "hcall": FakeHost()}), {})
    agent.iperf_sessions["abcdef123456"] = {
        "session_id": "abcdef123456",
        "host": "hcall",
        "port": 5201,
        "pid": "4242",
    }
    response = agent._run_iperf_client({
        "session_id": "abcdef123456",
        "source": "h20_01",
        "destination_ip": "198.51.100.20",
        "port": 5201,
        "protocol": "tcp",
        "seconds": 5,
    })
    assert response["ok"] is False
    assert response["error_code"] == "IPERF_JSON_INVALID"
    assert response["parse_warning"]


def test_same_destination_is_busy_but_different_destination_can_start(monkeypatch):
    module = load_topology_module(monkeypatch)
    h90 = FakeHost(["4101 1\n"])
    hcall = FakeHost(["4102 1\n"])
    agent = module.MininetControlAgent(FakeNet({"h90": h90, "hcall": hcall}), {})

    first = agent._start_iperf_server(start_request("abcdef123456", "h90", 5201))
    same = agent._start_iperf_server(start_request("abcdef123457", "h90", 5202))
    other = agent._start_iperf_server(start_request("abcdef123458", "hcall", 5203))

    assert first["ok"] is True
    assert same["ok"] is False
    assert same["error_code"] == "IPERF_DESTINATION_BUSY"
    assert other["ok"] is True
    assert first["port"] != other["port"]


def test_health_responds_while_udp_worker_is_running(monkeypatch):
    module = load_topology_module(monkeypatch)
    entered = threading.Event()
    release = threading.Event()

    class BlockingHost(FakeHost):
        def cmd(self, command):
            self.commands.append(command)
            entered.set()
            release.wait(timeout=2)
            return json.dumps({
                "end": {
                    "sum": {
                        "bits_per_second": 10_000_000,
                        "bytes": 1_250_000,
                        "jitter_ms": 1,
                        "lost_percent": 0,
                        "lost_packets": 0,
                    },
                },
            })

    agent = module.MininetControlAgent(
        FakeNet({"h30_01": BlockingHost(), "h90": FakeHost()}),
        {},
        token="test-token",
    )
    agent.iperf_sessions["abcdef123456"] = {
        "session_id": "abcdef123456",
        "host": "h90",
        "port": 5201,
        "pid": "4242",
    }
    result = {}
    worker = threading.Thread(target=lambda: result.update(agent._run_iperf_client({
        "session_id": "abcdef123456",
        "source": "h30_01",
        "destination_ip": "172.16.90.10",
        "port": 5201,
        "protocol": "udp",
        "seconds": 5,
    })))
    worker.start()
    assert entered.wait(timeout=2)
    health = agent._handle_request({"token": "test-token", "command": "HEALTH"})
    release.set()
    worker.join(timeout=2)

    assert health["ok"] is True
    assert health["agent_alive"] is True
    assert result["ok"] is True


def test_client_disconnect_after_run_cleans_owned_session(monkeypatch):
    module = load_topology_module(monkeypatch)
    source = FakeHost([json.dumps({
        "end": {
            "sum": {
                "bits_per_second": 10_000_000,
                "bytes": 1_250_000,
                "jitter_ms": 1,
                "lost_percent": 0,
                "lost_packets": 0,
            },
        },
    })])
    destination = FakeHost()
    agent = module.MininetControlAgent(
        FakeNet({"h30_01": source, "h90": destination}),
        {},
        token="test-token",
    )
    agent.iperf_sessions["abcdef123456"] = {
        "session_id": "abcdef123456",
        "host": "h90",
        "port": 5201,
        "pid": "4242",
    }

    class DisconnectingConnection:
        def __init__(self):
            self.read = False

        def settimeout(self, _timeout):
            return None

        def recv(self, _size):
            if self.read:
                return b""
            self.read = True
            return (json.dumps({
                "token": "test-token",
                "command": "RUN_IPERF_CLIENT",
                "request_id": "disconnect-run",
                "session_id": "abcdef123456",
                "source": "h30_01",
                "destination_ip": "172.16.90.10",
                "port": 5201,
                "protocol": "udp",
                "seconds": 5,
            }) + "\n").encode("utf-8")

        def sendall(self, _payload):
            raise BrokenPipeError("client disconnected")

        def close(self):
            return None

    agent._serve_connection(DisconnectingConnection())
    assert "abcdef123456" not in agent.iperf_sessions
    assert any("kill -TERM 4242" in command for command in destination.commands)
    assert agent._handle_request({"token": "test-token", "command": "HEALTH"})["ok"] is True
