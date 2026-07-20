from __future__ import annotations

import json
import os
import socket
import uuid
from pathlib import Path
from typing import Any


CONTROL_SOCKET = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
CONTROL_TOKEN = os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
SHORT_TIMEOUT_SECONDS = 3.0
START_IPERF_TIMEOUT_SECONDS = 5.0
FLOW_TIMEOUT_SECONDS = 5.0
IPERF_SAFETY_MARGIN_SECONDS = 10.0
PING_SAFETY_MARGIN_SECONDS = 3.0
MAX_REQUEST_TIMEOUT_SECONDS = 45.0
MAX_RESPONSE_BYTES = 128 * 1024


def _unavailable(
    message: str | None = None,
    error_code: str = "AGENT_NOT_READY",
) -> dict[str, Any]:
    return {
        "ok": False,
        "available": False,
        "error_code": error_code,
        "message": message or "Mininet control agent chua san sang. Hay chay sdn_mpls_demo/run_topology.sh.",
    }


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def timeout_for_command(command: str, payload: dict[str, Any] | None = None) -> float:
    values = payload or {}
    if command == "RUN_IPERF_CLIENT":
        seconds = _bounded_int(values.get("seconds"), 5, 1, 30)
        return min(float(seconds) + IPERF_SAFETY_MARGIN_SECONDS, MAX_REQUEST_TIMEOUT_SECONDS)
    if command == "PING":
        count = _bounded_int(values.get("count"), 3, 1, 10)
        ping_timeout = _bounded_int(values.get("ping_timeout"), 1, 1, 5)
        return min(float(count * ping_timeout) + PING_SAFETY_MARGIN_SECONDS, MAX_REQUEST_TIMEOUT_SECONDS)
    if command == "START_IPERF_SERVER":
        return START_IPERF_TIMEOUT_SECONDS
    if command in {"DUMP_FLOWS", "ADD_MANUAL_DROP", "DEL_COOKIE_FLOWS", "RELOAD_FIREWALL"}:
        return FLOW_TIMEOUT_SECONDS
    return SHORT_TIMEOUT_SECONDS


def _request_timeout(command: str, timeout_seconds: float | None, payload: dict[str, Any]) -> float:
    if timeout_seconds is None:
        return timeout_for_command(command, payload)
    try:
        requested = float(timeout_seconds)
    except (TypeError, ValueError):
        requested = timeout_for_command(command, payload)
    return max(1.0, min(requested, MAX_REQUEST_TIMEOUT_SECONDS))


def _timeout_response(command: str, timeout_seconds: float) -> dict[str, Any]:
    return {
        "ok": False,
        "available": True,
        "error_code": "AGENT_TIMEOUT",
        "command": command,
        "timeout_seconds": timeout_seconds,
        "message": (
            f"Mininet control agent khong tra loi lenh {command} "
            f"trong {timeout_seconds:g} giay. Agent van co the dang xu ly tac vu dai."
        ),
    }


def request_agent(
    command: str,
    timeout_seconds: float | None = None,
    **payload: Any,
) -> dict[str, Any]:
    if not hasattr(socket, "AF_UNIX"):
        return _unavailable(
            "He dieu hanh hien tai khong ho tro Unix socket cho Mininet control agent.",
            "AGENT_NOT_READY",
        )
    if not CONTROL_SOCKET.exists():
        return _unavailable(error_code="MININET_NOT_RUNNING")

    request_id = uuid.uuid4().hex
    request = {"token": CONTROL_TOKEN, "command": command, "request_id": request_id, **payload}
    effective_timeout = _request_timeout(command, timeout_seconds, payload)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(effective_timeout)
            client.connect(str(CONTROL_SOCKET))
            client.sendall((json.dumps(request) + "\n").encode("utf-8"))
            chunks: list[bytes] = []
            received = 0
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_RESPONSE_BYTES:
                    return _unavailable("Mininet control agent tra ve response qua lon.")
                newline = chunk.find(b"\n")
                if newline >= 0:
                    chunks.append(chunk[:newline])
                    break
                chunks.append(chunk)
        if not chunks:
            return _unavailable("Mininet control agent khong tra du lieu.", "AGENT_DISCONNECTED")
        response = json.loads(b"".join(chunks).decode("utf-8"))
        if response.get("request_id") != request_id:
            return _unavailable("Mininet control agent tra ve request_id khong khop.", "AGENT_NOT_READY")
        response.setdefault("available", True)
        return response
    except (socket.timeout, TimeoutError):
        return _timeout_response(command, effective_timeout)
    except OSError as exc:
        return _unavailable(f"Khong ket noi duoc Mininet control agent: {exc}", "AGENT_DISCONNECTED")
    except json.JSONDecodeError as exc:
        return _unavailable(f"Mininet control agent tra ve JSON khong hop le: {exc}", "AGENT_NOT_READY")


def health() -> dict[str, Any]:
    return request_agent("HEALTH")


def reload_firewall() -> dict[str, Any]:
    return request_agent("RELOAD_FIREWALL")


def set_link_state(link_id: str, state: str) -> dict[str, Any]:
    if state not in {"up", "down"}:
        return {"ok": False, "available": False, "message": "Trang thai link khong hop le."}
    command = "LINK_UP" if state == "up" else "LINK_DOWN"
    return request_agent(command, link_id=link_id)


def get_link_status() -> dict[str, Any]:
    return request_agent("GET_LINK_STATUS")


def live_status() -> dict[str, Any]:
    return request_agent("LIVE_STATUS")


def ping(source: str, destination_ip: str, count: int) -> tuple[bool, str]:
    response = ping_detailed(source, destination_ip, count)
    return bool(response.get("ok")), str(response.get("raw") or response.get("message") or "")


def ping_detailed(source: str, destination_ip: str, count: int) -> dict[str, Any]:
    return request_agent("PING", source=source, destination_ip=destination_ip, count=count)


def start_iperf_server(destination: str, port: int, log_path: str, session_id: str) -> dict[str, Any]:
    return request_agent(
        "START_IPERF_SERVER",
        destination=destination,
        port=port,
        log_path=log_path,
        session_id=session_id,
    )


def run_iperf_client(
    source: str,
    destination_ip: str,
    port: int,
    protocol: str,
    seconds: int,
    session_id: str,
) -> dict[str, Any]:
    return request_agent(
        "RUN_IPERF_CLIENT",
        source=source,
        destination_ip=destination_ip,
        port=port,
        protocol=protocol,
        seconds=seconds,
        session_id=session_id,
    )


def kill_pid(host: str, pid: str, session_id: str) -> dict[str, Any]:
    return request_agent("KILL_PID", host=host, pid=pid, session_id=session_id)


def dump_flows(switch: str) -> tuple[bool, str]:
    response = request_agent("DUMP_FLOWS", switch=switch)
    return bool(response.get("ok")), str(response.get("raw") or response.get("message") or "")


def bridge_exists(switch: str) -> tuple[bool, str]:
    response = request_agent("OVS_BR_EXISTS", switch=switch)
    return bool(response.get("ok")), str(response.get("message") or "")


def add_manual_drop(switch: str, cookie: int, source_ip: str, destination_ip: str) -> tuple[bool, str]:
    response = request_agent(
        "ADD_MANUAL_DROP",
        switch=switch,
        cookie=f"0x{cookie:x}",
        source_ip=source_ip,
        destination_ip=destination_ip,
    )
    return bool(response.get("ok")), str(response.get("raw") or response.get("message") or "")


def delete_cookie_flows(switch: str, cookie: int, cookie_mask: str) -> tuple[bool, str]:
    response = request_agent("DEL_COOKIE_FLOWS", switch=switch, cookie_match=f"0x{cookie:x}/{cookie_mask}")
    return bool(response.get("ok")), str(response.get("raw") or response.get("message") or "")


def first_down_link(path: list[str]) -> dict[str, Any] | None:
    status = get_link_status()
    if not status.get("ok"):
        return None
    links = status.get("links", {})
    for left, right in zip(path, path[1:]):
        forward = f"{left}-{right}"
        reverse = f"{right}-{left}"
        if links.get(forward) == "down":
            return {"link_id": forward, "blocked_at": left}
        if links.get(reverse) == "down":
            return {"link_id": reverse, "blocked_at": left}
    return None
