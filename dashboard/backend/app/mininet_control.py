from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any


CONTROL_SOCKET = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
CONTROL_TOKEN = os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
REQUEST_TIMEOUT_SECONDS = 3


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

    request = {"token": CONTROL_TOKEN, "command": command, **payload}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(REQUEST_TIMEOUT_SECONDS)
            client.connect(str(CONTROL_SOCKET))
            client.sendall((json.dumps(request) + "\n").encode("utf-8"))
            chunks: list[bytes] = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        if not chunks:
            return _unavailable("Mininet control agent khong tra du lieu.")
        response = json.loads(b"".join(chunks).decode("utf-8"))
        response.setdefault("available", True)
        return response
    except (OSError, TimeoutError) as exc:
        return _unavailable(f"Khong ket noi duoc Mininet control agent: {exc}")
    except json.JSONDecodeError as exc:
        return _unavailable(f"Mininet control agent tra ve JSON khong hop le: {exc}")


def set_link_state(link_id: str, state: str) -> dict[str, Any]:
    if state not in {"up", "down"}:
        return {"ok": False, "available": False, "message": "Trang thai link khong hop le."}
    command = "LINK_UP" if state == "up" else "LINK_DOWN"
    return request_agent(command, link_id=link_id)


def get_link_status() -> dict[str, Any]:
    return request_agent("GET_LINK_STATUS")


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

