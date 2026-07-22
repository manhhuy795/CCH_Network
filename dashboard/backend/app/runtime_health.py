from __future__ import annotations

import socket
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from . import mininet_control
from scripts.network_model import enforcement_switches, load_network_model


Status = str
TcpProbe = Callable[[str, int, float], tuple[bool, float | None, str | None]]
_WEBSOCKET_LOCK = threading.Lock()
_ACTIVE_WEBSOCKETS = 0
REQUIRED_ENFORCEMENT_SWITCHES = enforcement_switches(load_network_model())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def websocket_connected() -> None:
    global _ACTIVE_WEBSOCKETS
    with _WEBSOCKET_LOCK:
        _ACTIVE_WEBSOCKETS += 1


def websocket_disconnected() -> None:
    global _ACTIVE_WEBSOCKETS
    with _WEBSOCKET_LOCK:
        _ACTIVE_WEBSOCKETS = max(0, _ACTIVE_WEBSOCKETS - 1)


def active_websockets() -> int:
    with _WEBSOCKET_LOCK:
        return _ACTIVE_WEBSOCKETS


def tcp_probe(host: str, port: int, timeout: float = 0.4) -> tuple[bool, float | None, str | None]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = round((time.perf_counter() - started) * 1000, 2)
            return True, latency, None
    except OSError as exc:
        return False, None, str(exc)


def component(
    status: Status,
    message_vi: str,
    *,
    checked_at: str,
    latency_ms: float | None = None,
    error_code: str | None = None,
    technical_detail: Any = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "message_vi": message_vi,
        "checked_at": checked_at,
        "latency_ms": latency_ms,
        "error_code": error_code,
        "technical_detail": technical_detail,
    }


def _agent_error_code(response: dict[str, Any]) -> str:
    code = str(response.get("error_code") or "")
    if code in {"AGENT_TIMEOUT", "AGENT_DISCONNECTED", "MININET_NOT_RUNNING", "AGENT_NOT_READY"}:
        return code
    return "AGENT_NOT_READY"


def _flow_inventory(checked_at: str) -> dict[str, Any]:
    total = 0
    details = {}
    for switch in REQUIRED_ENFORCEMENT_SWITCHES:
        ok, output = mininet_control.dump_flows(switch)
        count = sum(
            1
            for line in output.splitlines()
            if "actions=" in line and "OFPST" not in line and "NXST" not in line
        ) if ok else 0
        details[switch] = {"ok": ok, "flow_count": count}
        if not ok:
            return component(
                "degraded",
                f"Khong doc duoc flow OpenFlow tren {switch}.",
                checked_at=checked_at,
                error_code="OVS_UNAVAILABLE",
                technical_detail=details,
            )
        total += count
    if total == 0:
        return component(
            "degraded",
            "OVS dang chay nhung chua co flow OpenFlow trong inventory.",
            checked_at=checked_at,
            error_code="FLOW_INVENTORY_EMPTY",
            technical_detail=details,
        )
    return component(
        "online",
        f"Da doc {total} flow OpenFlow tu {', '.join(REQUIRED_ENFORCEMENT_SWITCHES)}.",
        checked_at=checked_at,
        technical_detail=details,
    )


def system_health(
    *,
    probe: TcpProbe = tcp_probe,
    agent_health: Callable[[], dict[str, Any]] = mininet_control.health,
    live_status: Callable[[], dict[str, Any]] = mininet_control.live_status,
    include_flow_inventory: bool = True,
) -> dict[str, Any]:
    checked_at = now_iso()
    components: dict[str, dict[str, Any]] = {
        "backend": component(
            "online",
            "FastAPI dang xu ly request health.",
            checked_at=checked_at,
        ),
    }

    frontend_ok, frontend_latency, frontend_error = probe("127.0.0.1", 5173, 0.4)
    components["frontend"] = component(
        "online" if frontend_ok else "offline",
        "React frontend dang lang nghe cong 5173." if frontend_ok else "Khong ket noi duoc React frontend cong 5173.",
        checked_at=checked_at,
        latency_ms=frontend_latency,
        error_code=None if frontend_ok else "FRONTEND_OFFLINE",
        technical_detail=frontend_error,
    )

    controller_ok, controller_latency, controller_error = probe("127.0.0.1", 6653, 0.4)
    components["controller"] = component(
        "online" if controller_ok else "offline",
        "OS-Ken Controller dang lang nghe cong 6653." if controller_ok else "OS-Ken Controller khong lang nghe cong 6653.",
        checked_at=checked_at,
        latency_ms=controller_latency,
        error_code=None if controller_ok else "CONTROLLER_OFFLINE",
        technical_detail=controller_error,
    )

    agent_started = time.perf_counter()
    agent_response = agent_health()
    agent_latency = round((time.perf_counter() - agent_started) * 1000, 2)
    agent_ok = bool(agent_response.get("ok") and agent_response.get("agent_alive"))
    agent_code = None if agent_ok else _agent_error_code(agent_response)
    components["mininet_control_agent"] = component(
        "online" if agent_ok else ("degraded" if agent_code == "AGENT_TIMEOUT" else "offline"),
        "Mininet Control Agent phan hoi HEALTH." if agent_ok else str(agent_response.get("message") or "Mininet Control Agent khong phan hoi."),
        checked_at=checked_at,
        latency_ms=agent_latency,
        error_code=agent_code,
        technical_detail={
            key: value
            for key, value in agent_response.items()
            if key not in {"message", "message_vi", "token"}
        },
    )

    runtime: dict[str, Any] = {}
    if agent_ok:
        runtime = live_status()
    topology_ok = bool(runtime.get("ok") and int(runtime.get("user_hosts_online") or 0) > 0)
    topology_code = None if topology_ok else ("MININET_NOT_RUNNING" if not agent_ok else "AGENT_NOT_READY")
    components["mininet_topology"] = component(
        "online" if topology_ok else "offline",
        (
            f"Topology Mininet co {runtime.get('user_hosts_online', 0)} user host online."
            if topology_ok
            else "Khong xac nhan duoc topology Mininet dang hoat dong."
        ),
        checked_at=checked_at,
        error_code=topology_code,
        technical_detail={
            "user_hosts_online": runtime.get("user_hosts_online", 0),
            "mnexec": runtime.get("mnexec", False),
        },
    )

    bridges = runtime.get("bridges", {}) if isinstance(runtime.get("bridges"), dict) else {}
    required_bridges = set(REQUIRED_ENFORCEMENT_SWITCHES)
    live_bridges = {name for name in required_bridges if bridges.get(name)}
    ovs_ok = bool(runtime.get("ovs_bridge") and live_bridges == required_bridges)
    ovs_status = "online" if ovs_ok else ("degraded" if live_bridges else "offline")
    components["openvswitch"] = component(
        ovs_status,
        (
            f"Open vSwitch {', '.join(REQUIRED_ENFORCEMENT_SWITCHES)} dang hoat dong."
            if ovs_ok
            else "Khong xac nhan duoc day du bridge OVS bat buoc."
        ),
        checked_at=checked_at,
        error_code=None if ovs_ok else "OVS_UNAVAILABLE",
        technical_detail={"bridges": bridges, "required": sorted(required_bridges)},
    )

    ws_count = active_websockets()
    components["websocket"] = component(
        "online" if ws_count else "unknown",
        f"Co {ws_count} WebSocket metrics dang ket noi." if ws_count else "WebSocket endpoint san sang, hien khong co client ket noi.",
        checked_at=checked_at,
        technical_detail={"active_connections": ws_count},
    )

    components["flow_inventory"] = (
        _flow_inventory(checked_at)
        if include_flow_inventory and ovs_ok
        else component(
            "unknown" if not ovs_ok else "degraded",
            "Chua the doc flow inventory khi OVS chua san sang." if not ovs_ok else "Flow inventory chua duoc kiem tra.",
            checked_at=checked_at,
            error_code="OVS_UNAVAILABLE" if not ovs_ok else None,
        )
    )

    required = ("backend", "controller", "mininet_topology", "mininet_control_agent", "openvswitch")
    healthy = all(components[name]["status"] == "online" for name in required)
    all_statuses = {item["status"] for item in components.values()}
    overall = "online" if healthy and all_statuses <= {"online", "unknown"} else (
        "offline" if any(components[name]["status"] == "offline" for name in required) else "degraded"
    )
    return {
        "ok": healthy,
        "status": overall,
        "message_vi": "He thong san sang." if healthy else "He thong chua san sang day du. Xem tung component.",
        "checked_at": checked_at,
        "components": components,
        "runtime": runtime,
    }


def live_health_payload() -> dict[str, Any]:
    snapshot = system_health()
    runtime = snapshot.get("runtime") if isinstance(snapshot.get("runtime"), dict) else {}
    return {
        **runtime,
        **snapshot,
        "available": snapshot["components"]["mininet_control_agent"]["status"] == "online",
    }
