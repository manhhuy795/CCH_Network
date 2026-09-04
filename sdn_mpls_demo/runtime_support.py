#!/usr/bin/env python3
"""Shared runtime primitives for the enterprise Full-SDN topology."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import socket
import stat
import threading
import uuid
from pathlib import Path

from mininet.node import Node, OVSKernelSwitch, Switch

try:
    from scripts.network_model import (
        dpid_map,
        endpoint_link_segments,
        load_network_model,
        runtime_switch_map,
        runtime_switch_name,
    )
    from sdn_mpls_demo.firewall_nftables import (
        FIREWALL_NAMES,
        apply_to_mininet,
    )
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.network_model import (
        dpid_map,
        endpoint_link_segments,
        load_network_model,
        runtime_switch_map,
        runtime_switch_name,
    )
    from firewall_nftables import (
        FIREWALL_NAMES,
        apply_to_mininet,
    )


BASE_DIR = Path(__file__).resolve().parent
CONTROL_SOCKET = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
CONTROL_TOKEN = os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
CONTROL_PROTOCOL_VERSION = 1
CONTROL_MAX_REQUEST_BYTES = 128 * 1024
CONTROL_CONNECTION_TIMEOUT_SECONDS = 5
CONTROL_START_TIMEOUT_SECONDS = 5
CONTROL_AGENT_LOG = BASE_DIR / "runtime" / "mininet_control_agent.log"
SERIALIZED_MININET_COMMANDS = frozenset({
    "GET_TOPOLOGY",
    "GET_LINK_STATUS",
    "GET_HOST_STATUS",
    "GET_INTERFACE_MAP",
    "LIVE_STATUS",
    "PING",
    "DUMP_FLOWS",
    "OVS_BR_EXISTS",
    "ADD_MANUAL_DROP",
    "DEL_COOKIE_FLOWS",
    "RELOAD_FIREWALL",
    "FIREWALL_STATUS",
    "LINK_DOWN",
    "LINK_UP",
})
ALLOWED_CONTROL_COMMANDS = {
    "HEALTH",
    "PING_AGENT",
    "GET_TOPOLOGY",
    "GET_LINK_STATUS",
    "LINK_DOWN",
    "LINK_UP",
    "GET_HOST_STATUS",
    "GET_INTERFACE_MAP",
    "LIVE_STATUS",
    "PING",
    "START_IPERF_SERVER",
    "RUN_IPERF_CLIENT",
    "KILL_PID",
    "DUMP_FLOWS",
    "OVS_BR_EXISTS",
    "ADD_MANUAL_DROP",
    "DEL_COOKIE_FLOWS",
    "RELOAD_FIREWALL",
    "FIREWALL_STATUS",
}

NETWORK_MODEL = load_network_model()
DPIDS = dpid_map(NETWORK_MODEL)

# Linux interface names are limited to 15 bytes. Keep the source-of-truth ID
# and DPID authoritative while using a short bridge name in the Linux runtime.
RUNTIME_NODE_NAMES = runtime_switch_map(NETWORK_MODEL)


class ReliableOVSKernelSwitch(OVSKernelSwitch):
    """Create large OVS switches in bounded transactions."""

    def vsctl(self, *args, **kwargs):
        if self.batch:
            command = " ".join(str(arg).strip() for arg in args)
            self.commands.append(command)
            return None
        return self.cmd("ovs-vsctl", "--timeout=30", *args, **kwargs)

    def start(self, controllers):
        """Avoid one timeout-prone ovs-vsctl transaction for 60+ access ports."""
        if self.inNamespace:
            raise Exception("OVS kernel switch does not work in a namespace")
        int(self.dpid, 16)

        controller_args = []
        for controller in controllers:
            controller_args.append(
                f'-- --id=@{self.name}{controller.name} create Controller '
                f'target=\\"{controller.protocol}:{controller.IP()}:{controller.port}\\"'
            )
        if self.listenPort:
            controller_args.append(
                f'-- --id=@{self.name}-listen create Controller target="ptcp:{self.listenPort}"'
            )
        controller_ids = ",".join(f"@{self.name}{controller.name}" for controller in controllers)
        if self.listenPort:
            controller_ids += f",@{self.name}-listen"
        delete_existing = f" -- --if-exists del-br {self}" if not self.isOldOVS() else ""
        create_command = (
            " ".join(controller_args)
            + delete_existing
            + f" -- add-br {self}"
            + f" -- set bridge {self} controller=[{controller_ids}]"
            + self.bridgeOpts()
        )
        self.vsctl(create_command)

        for intf in self.intfList():
            if self.ports[intf] and not intf.IP():
                self.vsctl(
                    f"-- add-port {self} {intf}"
                    + self.intfOpts(intf)
                )


def runtime_node_name(logical_name: str) -> str:
    return runtime_switch_name(NETWORK_MODEL, logical_name)


LOGICAL_LINK_SEGMENTS: dict[str, list[tuple[str, str]]] = {}


class LinuxRouter(Node):
    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1 >/dev/null")
        self.cmd("sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null")
        self.cmd("sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0 >/dev/null")
        super().terminate()


class LinuxBridgeSwitch(Switch):
    """Small kernel Linux bridge used only for the Internet service LAN."""

    def start(self, _controllers):
        self.cmd("ip link add name", self.name, "type bridge")
        self.cmd("ip link set dev", self.name, "up")
        for interface in self.intfList():
            if str(interface) == "lo":
                continue
            self.cmd("ip link set dev", interface, "master", self.name)
            self.cmd("ip link set dev", interface, "up")

    def stop(self, deleteIntfs=True):
        self.cmd("ip link set dev", self.name, "down")
        self.cmd("ip link delete", self.name, "type bridge")
        super().stop(deleteIntfs)


class MininetControlAgent:
    """Small allowlisted control plane for the dashboard.

    The FastAPI backend talks to this agent over a Unix socket. The agent runs
    inside the topology process, so LINK_DOWN/LINK_UP can call Mininet APIs
    against real interfaces instead of storing simulated state in the backend.
    """

    def __init__(
        self,
        net,
        policy: dict,
        socket_path: Path | str = CONTROL_SOCKET,
        token: str = CONTROL_TOKEN,
    ):
        self.net = net
        self.policy = policy
        self.socket_path = Path(socket_path)
        self.token = token
        self.running = False
        self.thread: threading.Thread | None = None
        self.link_state: dict[str, str] = {}
        self.server_socket: socket.socket | None = None
        self.ready = threading.Event()
        self.startup_error: BaseException | None = None
        self.workers: set[threading.Thread] = set()
        self.workers_lock = threading.Lock()
        # Mininet's in-process graph and node helpers are not thread-safe.
        # Keep socket workers concurrent while serializing runtime graph calls.
        self.runtime_lock = threading.RLock()
        self.iperf_sessions: dict[str, dict] = {}
        self.iperf_lock = threading.Lock()

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self._remove_stale_socket()
        self.running = True
        self.ready.clear()
        self.startup_error = None
        self.thread = threading.Thread(target=self._serve, name="cch-mininet-control", daemon=True)
        self.thread.start()
        if not self.ready.wait(CONTROL_START_TIMEOUT_SECONDS):
            self.stop()
            raise RuntimeError("Mininet control agent khong san sang trong thoi gian cho phep.")
        if self.startup_error:
            error = self.startup_error
            self.stop()
            raise RuntimeError(f"Khong khoi dong duoc Mininet control agent: {error}") from error
        print(f"Mininet control agent: {self.socket_path}", flush=True)

    def stop(self) -> None:
        self.running = False
        server = self.server_socket
        self.server_socket = None
        if server is not None:
            try:
                server.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            server.close()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=CONTROL_START_TIMEOUT_SECONDS)
        with self.workers_lock:
            workers = list(self.workers)
        for worker in workers:
            if worker is not threading.current_thread():
                worker.join(timeout=1)
        self._cleanup_all_iperf_sessions()
        self._remove_socket_file()

    def _serve(self) -> None:
        try:
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket = server
            server.bind(str(self.socket_path))
            self.socket_path.chmod(0o660)
            server.listen(16)
            server.settimeout(1)
            self.ready.set()
            while self.running:
                try:
                    conn, _addr = server.accept()
                except socket.timeout:
                    continue
                except OSError as exc:
                    if not self.running:
                        break
                    self._log_connection_error(None, None, exc)
                    continue
                worker = threading.Thread(
                    target=self._serve_connection,
                    args=(conn,),
                    name="cch-mininet-client",
                    daemon=True,
                )
                with self.workers_lock:
                    self.workers.add(worker)
                worker.start()
        except OSError as exc:
            self.startup_error = exc
            self._log_connection_error(None, None, exc)
            self.ready.set()
        finally:
            server = self.server_socket
            self.server_socket = None
            if server is not None:
                server.close()
            self._remove_socket_file()

    def _serve_connection(self, conn) -> None:
        request_id = uuid.uuid4().hex
        command = None
        request = None
        delivery_failed = False
        try:
            conn.settimeout(CONTROL_CONNECTION_TIMEOUT_SECONDS)
            request = self._read_request(conn)
            request_id = str(request.get("request_id") or request_id)
            command = request.get("command")
            response = self._handle_request(request)
            response["request_id"] = request_id
            response.setdefault("protocol_version", CONTROL_PROTOCOL_VERSION)
            conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, socket.timeout, json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            delivery_failed = isinstance(exc, (BrokenPipeError, ConnectionResetError))
            self._log_connection_error(command, request_id, exc)
            self._send_error_response(conn, command, request_id, exc)
        except Exception as exc:
            self._log_connection_error(command, request_id, exc)
            self._send_error_response(conn, command, request_id, exc)
        finally:
            if delivery_failed and command in {"START_IPERF_SERVER", "RUN_IPERF_CLIENT"} and request:
                self._cleanup_iperf_session(str(request.get("session_id", "")))
            try:
                conn.close()
            except OSError:
                pass
            with self.workers_lock:
                self.workers.discard(threading.current_thread())

    def _read_request(self, conn) -> dict:
        chunks = bytearray()
        while True:
            chunk = conn.recv(min(65536, CONTROL_MAX_REQUEST_BYTES + 1 - len(chunks)))
            if not chunk:
                if not chunks:
                    raise ConnectionResetError("Client dong ket noi truoc khi gui request.")
                raise ValueError("Request thieu ky tu newline ket thuc.")
            chunks.extend(chunk)
            newline = chunks.find(b"\n")
            if newline >= 0:
                payload = bytes(chunks[:newline])
                break
            if len(chunks) > CONTROL_MAX_REQUEST_BYTES:
                raise ValueError(f"Request vuot qua {CONTROL_MAX_REQUEST_BYTES} bytes.")
        if not payload.strip():
            raise ValueError("Request rong.")
        if len(payload) > CONTROL_MAX_REQUEST_BYTES:
            raise ValueError(f"Request vuot qua {CONTROL_MAX_REQUEST_BYTES} bytes.")
        request = json.loads(payload.decode("utf-8"))
        if not isinstance(request, dict):
            raise ValueError("Request JSON phai la object.")
        return request

    def _handle_request(self, request: dict) -> dict:
        command = request.get("command")
        if command in SERIALIZED_MININET_COMMANDS:
            with self.runtime_lock:
                return self._handle_request_unlocked(request)
        return self._handle_request_unlocked(request)

    def _handle_request_unlocked(self, request: dict) -> dict:
        if request.get("token") != self.token:
            return {
                "ok": False,
                "error_code": "UNAUTHORIZED",
                "message": "Unauthorized Mininet control request.",
            }
        command = request.get("command")
        if command not in ALLOWED_CONTROL_COMMANDS:
            return {
                "ok": False,
                "error_code": "COMMAND_NOT_ALLOWED",
                "message": f"Command not allowed: {command}",
            }
        if command in {"HEALTH", "PING_AGENT"}:
            return {
                "ok": True,
                "agent_alive": True,
                "protocol_version": CONTROL_PROTOCOL_VERSION,
            }
        if command == "GET_TOPOLOGY":
            return self._topology()
        if command == "GET_LINK_STATUS":
            return self._link_status()
        if command == "GET_HOST_STATUS":
            return self._host_status()
        if command == "GET_INTERFACE_MAP":
            return self._interface_map(request.get("link_id"))
        if command == "LIVE_STATUS":
            return self._live_status()
        if command == "PING":
            return self._ping(request)
        if command == "START_IPERF_SERVER":
            return self._start_iperf_server(request)
        if command == "RUN_IPERF_CLIENT":
            return self._run_iperf_client(request)
        if command == "KILL_PID":
            return self._kill_pid(request)
        if command == "DUMP_FLOWS":
            return self._dump_flows(request.get("switch"))
        if command == "OVS_BR_EXISTS":
            return self._bridge_exists(request.get("switch"))
        if command == "ADD_MANUAL_DROP":
            return self._add_manual_drop(request)
        if command == "DEL_COOKIE_FLOWS":
            return self._delete_cookie_flows(request)
        if command == "RELOAD_FIREWALL":
            firewall_status = apply_to_mininet(self.net)
            return {
                "ok": True,
                "engine": "nftables",
                "table": "inet cch_filter",
                "firewalls": {
                    name: {
                        "ok": status["ok"],
                        "rule_count": status["rule_count"],
                    }
                    for name, status in firewall_status.items()
                },
            }
        if command == "FIREWALL_STATUS":
            return self._firewall_status()
        link_id = str(request.get("link_id", ""))
        if command == "LINK_DOWN":
            return self._set_link(link_id, "down")
        if command == "LINK_UP":
            return self._set_link(link_id, "up")
        return {"ok": False, "message": f"Unhandled command: {command}"}

    def _send_error_response(self, conn, command, request_id: str, exc: BaseException) -> None:
        response = {
            "ok": False,
            "error_code": self._error_code(exc),
            "command": command,
            "request_id": request_id,
            "protocol_version": CONTROL_PROTOCOL_VERSION,
            "message": str(exc),
        }
        try:
            conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, socket.timeout, OSError):
            pass

    def _log_connection_error(self, command, request_id, exc: BaseException) -> None:
        record = {
            "event": "mininet_control_error",
            "command": command,
            "request_id": request_id,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        line = json.dumps(record, ensure_ascii=False)
        print(line, flush=True)
        try:
            CONTROL_AGENT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with CONTROL_AGENT_LOG.open("a", encoding="utf-8") as log_file:
                log_file.write(line + "\n")
        except OSError:
            pass

    @staticmethod
    def _error_code(exc: BaseException) -> str:
        if isinstance(exc, json.JSONDecodeError):
            return "INVALID_JSON"
        if isinstance(exc, UnicodeDecodeError):
            return "INVALID_ENCODING"
        if isinstance(exc, socket.timeout):
            return "CONNECTION_TIMEOUT"
        if isinstance(exc, ValueError) and "vuot qua" in str(exc):
            return "REQUEST_TOO_LARGE"
        if isinstance(exc, ValueError):
            return "INVALID_REQUEST"
        return "CONNECTION_ERROR"

    def _remove_stale_socket(self) -> None:
        if not self.socket_path.exists():
            return
        mode = self.socket_path.lstat().st_mode
        if not stat.S_ISSOCK(mode):
            raise RuntimeError(f"Khong xoa file khong phai socket: {self.socket_path}")
        if self._socket_is_active():
            raise RuntimeError(f"Mininet control agent dang chay: {self.socket_path}")
        try:
            self.socket_path.unlink()
        except Exception:
            pass

    def _socket_is_active(self) -> bool:
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.settimeout(0.2)
            probe.connect(str(self.socket_path))
            return True
        except OSError:
            return False
        finally:
            probe.close()

    def _remove_socket_file(self) -> None:
        try:
            if stat.S_ISSOCK(self.socket_path.lstat().st_mode):
                self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def _node(self, name: str):
        if not isinstance(name, str):
            return None
        try:
            return self.net.get(runtime_node_name(name))
        except KeyError:
            return None

    def _switch_name(self, value) -> str | None:
        switch = str(value or "")
        return switch if switch in DPIDS else None

    def _ip(self, value) -> str | None:
        try:
            return str(ipaddress.ip_address(str(value)))
        except ValueError:
            return None

    def _port(self, value) -> int | None:
        try:
            port = int(value)
        except (TypeError, ValueError):
            return None
        return port if 1024 <= port <= 65535 else None

    def _duration(self, value) -> int:
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return 5
        return max(1, min(seconds, 30))

    @staticmethod
    def _session_id(value) -> str | None:
        session_id = str(value or "")
        return session_id if re.fullmatch(r"[0-9a-f]{12}", session_id) else None

    def _ping(self, request: dict) -> dict:
        source = str(request.get("source", ""))
        destination_ip = self._ip(request.get("destination_ip"))
        count = max(1, min(int(request.get("count", 3)), 10))
        node = self._node(source)
        if not node or not destination_ip:
            return {"ok": False, "message": "PING request khong hop le.", "raw": ""}
        output = node.cmd(f"ping -c {count} -W 1 {destination_ip}")
        return {"ok": " 0% packet loss" in output or " 0.0% packet loss" in output, "raw": output}

    def _start_iperf_server(self, request: dict) -> dict:
        session_id = self._session_id(request.get("session_id"))
        destination = str(request.get("destination", ""))
        port = self._port(request.get("port"))
        log_path = str(request.get("log_path", ""))
        node = self._node(destination)
        service = NETWORK_MODEL.get("services", {}).get(destination, {})
        bind_ip = self._ip(service.get("ip"))
        bind_argument = f" -B {bind_ip}" if bind_ip else ""
        expected_log = f"/tmp/cch_iperf/{session_id}.json" if session_id else ""
        if not node or port is None or not session_id or log_path != expected_log:
            return {
                "ok": False,
                "error_code": "INVALID_IPERF_SERVER_REQUEST",
                "message": "START_IPERF_SERVER request khong hop le.",
                "raw": "",
            }
        with self.iperf_lock:
            if session_id in self.iperf_sessions:
                return {
                    "ok": False,
                    "error_code": "IPERF_SESSION_EXISTS",
                    "message": f"Session iperf {session_id} da ton tai.",
                    "session_id": session_id,
                    "raw": "",
                }
            if any(session.get("host") == destination for session in self.iperf_sessions.values()):
                return {
                    "ok": False,
                    "error_code": "IPERF_DESTINATION_BUSY",
                    "message": f"{destination} dang co session iperf khac.",
                    "session_id": session_id,
                    "host": destination,
                    "raw": "",
                }
            self.iperf_sessions[session_id] = {
                "session_id": session_id,
                "host": destination,
                "port": port,
                "pid": None,
                "log_path": log_path,
                "state": "starting",
            }
        command = (
            f"mkdir -p /tmp/cch_iperf; "
            f"iperf3 -s -1 -p {port}{bind_argument} --json > {log_path} 2>&1 & "
            "pid=$!; ready=0; "
            "for attempt in $(seq 1 20); do "
            f"if kill -0 $pid 2>/dev/null && ss -H -ltn 'sport = :{port}' | grep -q .; "
            "then ready=1; break; fi; "
            "sleep 0.05; "
            "done; "
            "printf '%s %s\n' \"$pid\" \"$ready\""
        )
        try:
            output = node.cmd(command)
        except Exception:
            with self.iperf_lock:
                self.iperf_sessions.pop(session_id, None)
            raise
        match = re.search(r"(?m)^(\d+)\s+([01])\s*$", output)
        if not match or match.group(2) != "1":
            if match:
                node.cmd(f"kill -TERM {match.group(1)} 2>/dev/null || true")
            with self.iperf_lock:
                self.iperf_sessions.pop(session_id, None)
            return {
                "ok": False,
                "error_code": "IPERF_SERVER_NOT_LISTENING",
                "message": f"iperf3 server tren {destination}:{port} khong vao trang thai LISTEN.",
                "session_id": session_id,
                "host": destination,
                "port": port,
                "listening": False,
                "raw": output,
            }
        pid = match.group(1)
        session = {
            "session_id": session_id,
            "host": destination,
            "port": port,
            "pid": pid,
            "log_path": log_path,
            "state": "listening",
        }
        with self.iperf_lock:
            self.iperf_sessions[session_id] = session
        return {
            "ok": True,
            **session,
            "listening": True,
            "raw": output,
        }

    def _run_iperf_client(self, request: dict) -> dict:
        session_id = self._session_id(request.get("session_id"))
        source = str(request.get("source", ""))
        destination_ip = self._ip(request.get("destination_ip"))
        port = self._port(request.get("port"))
        protocol = str(request.get("protocol", "tcp")).lower()
        seconds = self._duration(request.get("seconds", 5))
        node = self._node(source)
        with self.iperf_lock:
            session = dict(self.iperf_sessions.get(session_id, {})) if session_id else {}
        if (
            not node
            or not destination_ip
            or port is None
            or protocol not in {"tcp", "udp"}
            or not session_id
            or session.get("port") != port
        ):
            return {
                "ok": False,
                "error_code": "INVALID_IPERF_CLIENT_REQUEST",
                "message": "RUN_IPERF_CLIENT request khong hop le hoac session khong ton tai.",
                "session_id": session_id,
                "raw": "",
            }
        udp = " -u -b 20M" if protocol == "udp" else ""
        output = node.cmd(f"iperf3 -c {destination_ip} -p {port} -t {seconds} --json{udp}")
        try:
            payload = json.loads(output)
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "error_code": "IPERF_JSON_INVALID",
                "message": "iperf3 tra ve JSON khong hop le.",
                "session_id": session_id,
                "parse_warning": str(exc),
                "raw": output,
            }
        if not isinstance(payload, dict):
            return {
                "ok": False,
                "error_code": "IPERF_JSON_INVALID",
                "message": "iperf3 JSON phai la object.",
                "session_id": session_id,
                "parse_warning": f"Nhan duoc {type(payload).__name__} thay vi object.",
                "raw": output,
            }
        result, warnings = self._iperf_result(payload, protocol)
        error = payload.get("error")
        return {
            "ok": not error and bool(payload.get("end")),
            "error_code": "IPERF_CLIENT_ERROR" if error else None,
            "message": str(error or "iperf3 client hoan thanh."),
            "session_id": session_id,
            "protocol": protocol,
            "duration": seconds,
            "result": result,
            "parse_warning": "; ".join(warnings) if warnings else None,
            "raw": output,
        }

    def _kill_pid(self, request: dict) -> dict:
        session_id = self._session_id(request.get("session_id"))
        host = str(request.get("host", ""))
        pid = str(request.get("pid", ""))
        node = self._node(host)
        with self.iperf_lock:
            session = dict(self.iperf_sessions.get(session_id, {})) if session_id else {}
        if (
            not node
            or not re.fullmatch(r"\d+", pid)
            or not session_id
            or session.get("host") != host
            or session.get("pid") != pid
        ):
            return {
                "ok": False,
                "error_code": "IPERF_SESSION_OWNERSHIP_MISMATCH",
                "message": "PID khong thuoc dung host/session iperf.",
                "session_id": session_id,
                "raw": "",
            }
        output = node.cmd(f"kill -TERM {pid} 2>/dev/null || true")
        with self.iperf_lock:
            self.iperf_sessions.pop(session_id, None)
        return {"ok": True, "session_id": session_id, "pid": pid, "host": host, "raw": output}

    @staticmethod
    def _iperf_result(payload: dict, protocol: str) -> tuple[dict, list[str]]:
        end = payload.get("end") if isinstance(payload.get("end"), dict) else {}
        if protocol == "udp":
            summary = end.get("sum") if isinstance(end.get("sum"), dict) else {}
        else:
            summary = end.get("sum_received") if isinstance(end.get("sum_received"), dict) else {}
            if not summary and isinstance(end.get("sum"), dict):
                summary = end["sum"]
        warnings = []
        throughput = None
        if summary.get("bits_per_second") is not None:
            try:
                throughput = round(float(summary["bits_per_second"]) / 1_000_000, 3)
            except (TypeError, ValueError):
                warnings.append("Field bits_per_second khong phai so.")
        fields = {
            "throughput_mbps": throughput,
            "jitter_ms": summary.get("jitter_ms"),
            "packet_loss_percent": summary.get("lost_percent"),
            "lost_packets": summary.get("lost_packets"),
            "total_datagrams": summary.get("packets"),
            "transferred_bytes": summary.get("bytes"),
        }
        required = ["bits_per_second", "bytes"]
        if protocol == "udp":
            required.extend(["jitter_ms", "lost_percent", "lost_packets"])
        warnings.extend(f"Thieu field end summary: {field}" for field in required if field not in summary)
        return fields, warnings

    def _cleanup_iperf_session(self, session_id: str) -> None:
        with self.iperf_lock:
            session = self.iperf_sessions.pop(session_id, None)
        if not session:
            return
        node = self._node(str(session.get("host", "")))
        pid = str(session.get("pid", ""))
        if node and re.fullmatch(r"\d+", pid):
            node.cmd(f"kill -TERM {pid} 2>/dev/null || true")

    def _cleanup_all_iperf_sessions(self) -> None:
        with self.iperf_lock:
            session_ids = list(self.iperf_sessions)
        for session_id in session_ids:
            self._cleanup_iperf_session(session_id)

    def _dump_flows(self, switch_value) -> dict:
        switch = self._switch_name(switch_value)
        node = self._node(switch) if switch else None
        if not node:
            return {"ok": False, "message": "Switch khong hop le.", "raw": ""}
        output = node.cmd(f"ovs-ofctl -O OpenFlow13 dump-flows {node.name}")
        return {"ok": True, "raw": output}

    def _bridge_exists(self, switch_value) -> dict:
        switch = self._switch_name(switch_value)
        return {"ok": bool(switch and self._node(switch)), "switch": switch}

    def _add_manual_drop(self, request: dict) -> dict:
        switch = self._switch_name(request.get("switch"))
        node = self._node(switch) if switch else None
        src_ip = self._ip(request.get("source_ip"))
        dst_ip = self._ip(request.get("destination_ip"))
        cookie = str(request.get("cookie", ""))
        if not node or not src_ip or not dst_ip or not re.fullmatch(r"0x[0-9a-fA-F]+", cookie):
            return {"ok": False, "message": "ADD_MANUAL_DROP request khong hop le.", "raw": ""}
        flow = f"cookie={cookie},priority=500,ip,nw_src={src_ip},nw_dst={dst_ip},actions=drop"
        output = node.cmd(f"ovs-ofctl -O OpenFlow13 add-flow {node.name} '{flow}'")
        return {"ok": True, "raw": output}

    def _delete_cookie_flows(self, request: dict) -> dict:
        switch = self._switch_name(request.get("switch"))
        node = self._node(switch) if switch else None
        cookie_match = str(request.get("cookie_match", ""))
        if not node or not re.fullmatch(r"0x[0-9a-fA-F]+/0x[0-9a-fA-F]+", cookie_match):
            return {"ok": False, "message": "DEL_COOKIE_FLOWS request khong hop le.", "raw": ""}
        output = node.cmd(f"ovs-ofctl -O OpenFlow13 del-flows {node.name} cookie={cookie_match}")
        return {"ok": True, "raw": output}

    def _firewall_status(self) -> dict:
        """Read live nftables counters only from the two firewall namespaces."""
        status: dict[str, dict] = {}
        for firewall_name in FIREWALL_NAMES:
            node = self._node(firewall_name)
            if not node:
                status[firewall_name] = {
                    "ok": False,
                    "error_code": "FIREWALL_UNAVAILABLE",
                    "message": f"Khong tim thay namespace {firewall_name}.",
                }
                continue
            ruleset = node.cmd("nft -a list table inet cch_filter 2>&1")
            forwarding = node.cmd("sysctl -n net.ipv4.ip_forward 2>&1").strip()
            if "No such file" in ruleset or "Error" in ruleset or "error" in ruleset.lower():
                status[firewall_name] = {
                    "ok": False,
                    "error_code": "FIREWALL_RULESET_UNAVAILABLE",
                    "message": f"Chua doc duoc inet cch_filter tren {firewall_name}.",
                    "ipv4_forwarding": forwarding,
                }
                continue
            counters = {
                "social_deny": self._nft_counter(ruleset, "deny-social-media"),
                "call_allow": self._nft_counter(ruleset, "allow-call-app"),
                "zalo_allow": self._nft_counter(ruleset, "allow-zalo"),
                "inbound_deny": self._nft_counter(ruleset, "deny-inbound-new"),
                "established_related": self._nft_counter(ruleset, "forward-established"),
                "invalid_drop": self._nft_counter(ruleset, "forward-invalid"),
            }
            status[firewall_name] = {
                "ok": True,
                "table": "inet cch_filter",
                "chain": "forward",
                "rule_count": ruleset.count(" comment "),
                "counters": counters,
                "ipv4_forwarding": forwarding == "1",
                "raw": ruleset,
            }
        return {"ok": all(item.get("ok") for item in status.values()), "firewalls": status}

    @staticmethod
    def _nft_counter(ruleset: str, comment: str) -> dict[str, int] | None:
        for line in ruleset.splitlines():
            if comment not in line:
                continue
            match = re.search(r"counter packets (\d+) bytes (\d+)", line)
            if match:
                return {"packets": int(match.group(1)), "bytes": int(match.group(2))}
        return None

    def _logical_links(self) -> list[str]:
        return [f"{source}-{target}" for source, target, _kind in self.policy.get("links", [])]

    def _segments_for_link(self, link_id: str) -> list[tuple[str, str]]:
        if link_id in LOGICAL_LINK_SEGMENTS:
            return LOGICAL_LINK_SEGMENTS[link_id]
        if "-" not in link_id:
            return []
        left, right = link_id.split("-", 1)
        groups = self.policy.get("host_groups", {})
        if left in groups:
            segments = endpoint_link_segments(NETWORK_MODEL, left, right)
            if segments:
                return segments
        if right in groups:
            segments = endpoint_link_segments(NETWORK_MODEL, right, left)
            if segments:
                return [(switch, endpoint) for endpoint, switch in segments]
        return [(left, right)]

    def _segment_interface_map(self, left: str, right: str) -> dict:
        left_node = self._node(left)
        right_node = self._node(right)
        if left_node is None or right_node is None:
            return {"left": left, "right": right, "status": "missing", "interfaces": []}
        connections = left_node.connectionsTo(right_node)
        interfaces = [
            {
                "left": str(left_intf),
                "right": str(right_intf),
                "left_up": bool(left_intf.isUp()),
                "right_up": bool(right_intf.isUp()),
            }
            for left_intf, right_intf in connections
        ]
        if not interfaces:
            status = "missing"
        elif all(item["left_up"] and item["right_up"] for item in interfaces):
            status = "up"
        else:
            status = "down"
        return {"left": left, "right": right, "status": status, "interfaces": interfaces}

    def _link_runtime_status(self, link_id: str) -> str:
        if link_id in self.link_state:
            return self.link_state[link_id]
        segments = [self._segment_interface_map(left, right) for left, right in self._segments_for_link(link_id)]
        if not segments or any(item["status"] == "missing" for item in segments):
            return "unknown"
        return "up" if all(item["status"] == "up" for item in segments) else "down"

    def _set_link(self, link_id: str, state: str) -> dict:
        segments = self._segments_for_link(link_id)
        if not segments:
            return {"ok": False, "message": f"Khong tim thay mapping link {link_id}.", "link_id": link_id}
        changed = []
        for left, right in segments:
            try:
                left_node = self._node(left)
                right_node = self._node(right)
                if left_node is None or right_node is None:
                    raise KeyError(f"Missing runtime node for {left}-{right}")
                self.net.configLinkStatus(left_node.name, right_node.name, state)
                changed.append({"left": left, "right": right, "state": state})
            except Exception as exc:  # Mininet raises generic Exception for missing links.
                return {
                    "ok": False,
                    "message": f"Khong doi duoc trang thai {left}-{right}: {exc}",
                    "link_id": link_id,
                    "changed": changed,
                }
        self.link_state[link_id] = state
        return {
            "ok": True,
            "available": True,
            "message": f"Da chuyen link {link_id} sang {state} tren Mininet.",
            "link_id": link_id,
            "status": state,
            "changed": changed,
            "links": self._link_status()["links"],
            "interfaces": self._interface_map(link_id).get("interfaces", []),
        }

    def _link_status(self) -> dict:
        return {
            "ok": True,
            "available": True,
            "links": {link_id: self._link_runtime_status(link_id) for link_id in self._logical_links()},
        }

    def _interface_map(self, link_id: str | None = None) -> dict:
        link_ids = [link_id] if link_id else self._logical_links()
        mapping = {
            item: [
                self._segment_interface_map(left, right)
                for left, right in self._segments_for_link(item)
            ]
            for item in link_ids
            if item
        }
        return {"ok": True, "available": True, "interfaces": mapping.get(link_id, mapping)}

    def _host_status(self) -> dict:
        nodes = getattr(self.net, "nameToNode", {})
        return {
            "ok": True,
            "available": True,
            "hosts": {name: name in nodes for name in self.policy.get("hosts", {})},
        }

    def _live_status(self) -> dict:
        nodes = getattr(self.net, "nameToNode", {})
        hosts = {name: name in nodes for name in self.policy.get("hosts", {})}
        bridges = {switch: self._node(switch) is not None for switch in DPIDS}
        return {
            "ok": True,
            "available": True,
            "ovs_bridge": any(bridges.values()),
            "bridges": bridges,
            "mnexec": bool(shutil.which("mnexec")),
            "iperf3": bool(shutil.which("iperf3")),
            "hosts": hosts,
            "user_hosts_online": sum(
                1
                for name, host in self.policy.get("hosts", {}).items()
                if host.get("kind") == "user" and hosts.get(name)
            ),
        }

    def _topology(self) -> dict:
        return {"ok": True, "available": True, **self._link_status()}
