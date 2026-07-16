from __future__ import annotations

import json
import os
import socket
import uuid
from pathlib import Path
from typing import Any


CONTROL_SOCKET = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
CONTROL_TOKEN = os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
REQUEST_TIMEOUT_SECONDS = 3
MAX_RESPONSE_BYTES = 128 * 1024


def _unavailable(message: str | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "available": False,
        "message": message or "Mininet control agent chua san sang. Hay chay sdn_mpls_demo/run_topology.sh.",
    }


def request_agent(command: str, **payload: Any) -> dict[str, Any]:
    if not hasattr(socket, "AF_UNIX"):
        return _unavailable("He dieu hanh hien tai khong ho tro Unix socket cho Mininet control agent.")
    if not CONTROL_SOCKET.exists():
        return _unavailable()

    request_id = uuid.uuid4().hex
    request = {"token": CONTROL_TOKEN, "command": command, "request_id": request_id, **payload}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(REQUEST_TIMEOUT_SECONDS)
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
            return _unavailable("Mininet control agent khong tra du lieu.")
        response = json.loads(b"".join(chunks).decode("utf-8"))
        if response.get("request_id") != request_id:
            return _unavailable("Mininet control agent tra ve request_id khong khop.")
        response.setdefault("available", True)
        return response
    except (OSError, TimeoutError) as exc:
        return _unavailable(f"Khong ket noi duoc Mininet control agent: {exc}")
    except json.JSONDecodeError as exc:
        return _unavailable(f"Mininet control agent tra ve JSON khong hop le: {exc}")


def health() -> dict[str, Any]:
    return request_agent("HEALTH")


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
    response = request_agent("PING", source=source, destination_ip=destination_ip, count=count)
    return bool(response.get("ok")), str(response.get("raw") or response.get("message") or "")


def start_iperf_server(destination: str, port: int, log_path: str) -> tuple[bool, str]:
    response = request_agent("START_IPERF_SERVER", destination=destination, port=port, log_path=log_path)
    return bool(response.get("ok")), str(response.get("raw") or response.get("message") or "")


def run_iperf_client(source: str, destination_ip: str, port: int, protocol: str, seconds: int) -> tuple[bool, str]:
    response = request_agent(
        "RUN_IPERF_CLIENT",
        source=source,
        destination_ip=destination_ip,
        port=port,
        protocol=protocol,
        seconds=seconds,
    )
    return bool(response.get("ok")), str(response.get("raw") or response.get("message") or "")


def kill_pid(host: str, pid: str) -> tuple[bool, str]:
    response = request_agent("KILL_PID", host=host, pid=pid)
    return bool(response.get("ok")), str(response.get("raw") or response.get("message") or "")


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
