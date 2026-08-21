"""Small, honest runtime helpers for the redesigned Mininet lab.

These helpers never manufacture a result. Every PASS comes from an OVS query,
the live control-agent socket, or a real command executed in a Mininet host.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOCKET_PATH = Path(os.getenv("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
TOKEN = os.getenv("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
SWITCHES = (
    "access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2",
    "core_hq", "access_branch", "dist_branch", "infra_access",
)


def require_linux_root() -> None:
    if platform.system() != "Linux":
        raise RuntimeError("LIVE_RUNTIME_REQUIRES_LINUX")
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        raise RuntimeError("LIVE_RUNTIME_REQUIRES_ROOT")


def command(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def agent_request(command_name: str, timeout: float = 15.0, **payload: Any) -> dict[str, Any]:
    if not SOCKET_PATH.exists():
        raise RuntimeError("MININET_NOT_RUNNING")
    request_id = uuid.uuid4().hex
    request = {"token": TOKEN, "command": command_name, "request_id": request_id, **payload}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(SOCKET_PATH))
        client.sendall((json.dumps(request) + "\n").encode("utf-8"))
        data = b""
        while b"\n" not in data:
            chunk = client.recv(65536)
            if not chunk:
                break
            data += chunk
    if not data:
        raise RuntimeError("AGENT_DISCONNECTED")
    response = json.loads(data.split(b"\n", 1)[0].decode("utf-8"))
    if response.get("request_id") != request_id:
        raise RuntimeError("AGENT_NOT_READY")
    return response


def model_hosts() -> dict[str, dict[str, Any]]:
    from scripts.network_model import build_host_inventory, load_network_model

    return build_host_inventory(load_network_model())


def verify_fabric() -> dict[str, Any]:
    bridges = command(["ovs-vsctl", "list-br"]).stdout.splitlines()
    missing = sorted(set(SWITCHES) - set(bridges))
    if missing:
        raise RuntimeError(f"OVS_UNAVAILABLE:{','.join(missing)}")
    flow_counts: dict[str, int] = {}
    for switch in SWITCHES:
        result = command(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", switch])
        if result.returncode != 0:
            raise RuntimeError(f"OPENFLOW_UNAVAILABLE:{switch}")
        flow_counts[switch] = sum(1 for line in result.stdout.splitlines() if "cookie=" in line and "actions=" in line)
        if flow_counts[switch] == 0:
            raise RuntimeError(f"OPENFLOW_EMPTY:{switch}")
    health = agent_request("HEALTH")
    if health.get("ok") is not True or health.get("agent_alive") is not True:
        raise RuntimeError("AGENT_NOT_READY")
    live = agent_request("LIVE_STATUS")
    if live.get("ok") is not True or int(live.get("user_hosts_online", 0)) != 110:
        raise RuntimeError("MININET_TOPOLOGY_INVALID")
    return {"bridges": bridges, "flow_counts": flow_counts, "agent": health, "live": live}


def ping(source: str, destination: str, count: int = 2) -> dict[str, Any]:
    hosts = model_hosts()
    if source not in hosts or destination not in hosts:
        raise RuntimeError("UNKNOWN_ENDPOINT")
    started = time.monotonic()
    response = agent_request("PING", source=source, destination_ip=hosts[destination]["ip"], count=count)
    response["duration_seconds"] = round(time.monotonic() - started, 3)
    return response


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
