#!/usr/bin/env python3
from __future__ import annotations

import atexit
import concurrent.futures
import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT_DIR / "runtime_reports"
TOKEN_FILE = ROOT_DIR / "logs" / "operator.token"
BASE_URL = os.environ.get("CCH_DASHBOARD_API_URL", "http://127.0.0.1:8000").rstrip("/")
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG_FILE = REPORT_DIR / f"dashboard_runtime_{TIMESTAMP}.log"
JSON_FILE = REPORT_DIR / f"dashboard_runtime_{TIMESTAMP}.json"
RESULTS: list[dict[str, Any]] = []
TOKEN = ""
REPORT_SAVED = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    print(message, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as output:
        output.write(message + "\n")


def summarize(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return str(payload)[:300]
    decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    return {
        "ok": payload.get("ok"),
        "status": payload.get("status"),
        "message_vi": payload.get("message_vi") or payload.get("message"),
        "error_code": payload.get("error_code"),
        "action": decision.get("action"),
        "throughput_mbps": result.get("throughput_mbps"),
        "jitter_ms": result.get("jitter_ms"),
        "packet_loss_percent": result.get("packet_loss_percent"),
        "measurement_completed": payload.get("measurement_completed"),
    }


def record(
    name: str,
    passed: bool,
    started: float,
    *,
    error_code: str | None = None,
    summary: Any = None,
) -> bool:
    duration = round(time.perf_counter() - started, 3)
    item = {
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "duration_seconds": duration,
        "error_code": error_code,
        "response_summary": summary,
    }
    RESULTS.append(item)
    log(
        f"{item['status']:<4} {name} duration={duration:.3f}s "
        f"error_code={error_code or '-'} summary={json.dumps(summary, ensure_ascii=False)}"
    )
    return passed


def run_case(name: str, function: Callable[[], tuple[bool, str | None, Any]]) -> bool:
    started = time.perf_counter()
    try:
        passed, error_code, summary = function()
        return record(name, passed, started, error_code=error_code, summary=summary)
    except Exception as exc:
        return record(
            name,
            False,
            started,
            error_code=type(exc).__name__,
            summary=str(exc)[:500],
        )


def tcp_check(port: int, timeout: float = 2.0) -> tuple[bool, str | None, Any]:
    with socket.create_connection(("127.0.0.1", port), timeout=timeout):
        return True, None, {"port": port, "listening": True}


def command_check(command: list[str], *, contains: str | None = None) -> tuple[bool, str | None, Any]:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    output = (completed.stdout + completed.stderr).strip()
    passed = completed.returncode == 0 and (contains is None or contains in output)
    return passed, None if passed else "COMMAND_FAILED", {
        "command": command,
        "returncode": completed.returncode,
        "output": output[:500],
    }


def api_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: float = 45,
    authenticated: bool = False,
) -> tuple[int, dict[str, Any]]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if authenticated:
        headers["X-CCH-Operator-Token"] = TOKEN
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"message_vi": body[:500], "error_code": f"HTTP_{exc.code}"}
        return exc.code, parsed


def api_case(
    path: str,
    payload: dict[str, Any],
    validator: Callable[[int, dict[str, Any]], bool],
    *,
    timeout: float = 45,
) -> tuple[bool, str | None, Any]:
    status, response = api_request("POST", path, payload, timeout=timeout, authenticated=True)
    passed = validator(status, response)
    return passed, response.get("error_code") if isinstance(response, dict) else None, {
        "http_status": status,
        **summarize(response),
    }


def health_case() -> tuple[bool, str | None, Any]:
    status, payload = api_request("GET", "/api/health", timeout=15)
    components = payload.get("components", {})
    required = ("backend", "controller", "mininet_topology", "mininet_control_agent", "openvswitch")
    passed = status == 200 and all(components.get(name, {}).get("status") == "online" for name in required)
    component_summary = {
        name: {
            "status": item.get("status"),
            "error_code": item.get("error_code"),
        }
        for name, item in components.items()
    }
    return passed, None if passed else "HEALTH_DEGRADED", {
        "http_status": status,
        "system_status": payload.get("status"),
        "components": component_summary,
    }


def agent_health_case() -> tuple[bool, str | None, Any]:
    status, payload = api_request("GET", "/api/health", timeout=15)
    agent = payload.get("components", {}).get("mininet_control_agent", {})
    passed = status == 200 and agent.get("status") == "online"
    return passed, agent.get("error_code"), agent


def active_iperf_count() -> int:
    _status, payload = api_request(
        "GET",
        "/api/live/iperf-sessions",
        timeout=5,
        authenticated=True,
    )
    return int(payload.get("active_count") or 0)


def wait_for_active_iperf(timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if active_iperf_count() > 0:
            return True
        time.sleep(0.1)
    return False


def different_destination_concurrency_case() -> tuple[bool, str | None, Any]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(api_request, "POST", "/api/test/iperf", payload, timeout=45, authenticated=True)
            for payload in (
                {"source": "h30_01", "destination": "h90", "protocol": "udp", "seconds": 5},
                {"source": "h20_01", "destination": "hcall", "protocol": "udp", "seconds": 5},
            )
        ]
        responses = [future.result() for future in futures]
    passed = all(status == 200 and body.get("ok") is True for status, body in responses)
    error_code = next(
        (body.get("error_code") for _status, body in responses if body.get("error_code")),
        None,
    )
    return passed, error_code, [
        {"http_status": status, **summarize(body)}
        for status, body in responses
    ]


def same_destination_concurrency_case() -> tuple[bool, str | None, Any]:
    first_payload = {"source": "h30_01", "destination": "h90", "protocol": "udp", "seconds": 10}
    second_payload = {"source": "h20_01", "destination": "h90", "protocol": "udp", "seconds": 5}
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        first_future = executor.submit(
            api_request,
            "POST",
            "/api/test/iperf",
            first_payload,
            timeout=60,
            authenticated=True,
        )
        active_seen = wait_for_active_iperf()
        second_status, second_body = api_request(
            "POST",
            "/api/test/iperf",
            second_payload,
            timeout=15,
            authenticated=True,
        )
        first_status, first_body = first_future.result()
    passed = (
        active_seen
        and first_status == 200
        and first_body.get("ok") is True
        and second_status == 409
        and second_body.get("error_code") == "IPERF_BUSY"
    )
    return passed, None if passed else second_body.get("error_code"), {
        "active_session_seen": active_seen,
        "first": {"http_status": first_status, **summarize(first_body)},
        "second": {"http_status": second_status, **summarize(second_body)},
    }


def snapshot_log_offsets(paths: list[Path]) -> dict[Path, int]:
    return {path: path.stat().st_size if path.exists() else 0 for path in paths}


def new_log_content(path: Path, offset: int) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as source:
        source.seek(offset)
        return source.read().decode("utf-8", errors="replace")


def log_safety_case(offsets: dict[Path, int]) -> tuple[bool, str | None, Any]:
    fatal_patterns = (
        "BrokenPipeError",
        "Exception in thread cch-mininet-control",
        "Address already in use",
        "unhandled task exception",
    )
    findings = []
    for path, offset in offsets.items():
        content = new_log_content(path, offset)
        for pattern in fatal_patterns:
            if pattern.lower() in content.lower():
                findings.append({"file": str(path.relative_to(ROOT_DIR)), "pattern": pattern})
        if "ConnectionResetError" in content and (
            "Traceback" in content or "unhandled" in content.lower()
        ):
            findings.append({
                "file": str(path.relative_to(ROOT_DIR)),
                "pattern": "unhandled ConnectionResetError",
            })
    return not findings, "UNHANDLED_RUNTIME_LOG" if findings else None, {"findings": findings}


def save_report() -> None:
    global REPORT_SAVED
    if REPORT_SAVED or not REPORT_DIR.exists():
        return
    REPORT_SAVED = True
    passed = sum(1 for item in RESULTS if item["status"] == "PASS")
    report = {
        "suite": "CCH dashboard Ubuntu live runtime smoke",
        "created_at": utc_now(),
        "base_url": BASE_URL,
        "passed": passed,
        "failed": len(RESULTS) - passed,
        "total": len(RESULTS),
        "results": RESULTS,
        "log_file": str(LOG_FILE.relative_to(ROOT_DIR)),
    }
    JSON_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"ARTIFACT log={LOG_FILE.relative_to(ROOT_DIR)}")
    log(f"ARTIFACT json={JSON_FILE.relative_to(ROOT_DIR)}")
    log(f"RESULT {passed}/{len(RESULTS)} PASS")


def main() -> int:
    global TOKEN
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("", encoding="utf-8")
    atexit.register(save_report)
    if platform.system() != "Linux":
        record("linux_preflight", False, time.perf_counter(), error_code="LINUX_REQUIRED", summary=platform.system())
        return 2
    if os.geteuid() != 0:
        record("root_preflight", False, time.perf_counter(), error_code="ROOT_REQUIRED", summary="Chay bang sudo.")
        return 2
    if not TOKEN_FILE.is_file():
        record(
            "operator_token_preflight",
            False,
            time.perf_counter(),
            error_code="TOKEN_FILE_MISSING",
            summary=str(TOKEN_FILE.relative_to(ROOT_DIR)),
        )
        return 2
    TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not TOKEN:
        record("operator_token_preflight", False, time.perf_counter(), error_code="TOKEN_EMPTY", summary="Token file rong.")
        return 2
    log("Operator token da nap an toan; gia tri token khong duoc ghi vao report.")

    monitored_logs = [
        ROOT_DIR / "logs" / "backend.log",
        ROOT_DIR / "logs" / "frontend.log",
        ROOT_DIR / "logs" / "controller.log",
        ROOT_DIR / "sdn_mpls_demo" / "runtime" / "controller.log",
        ROOT_DIR / "sdn_mpls_demo" / "runtime" / "mininet_control_agent.log",
    ]
    offsets = snapshot_log_offsets(monitored_logs)

    run_case("controller_port_6653", lambda: tcp_check(6653))
    run_case("backend_port_8000", lambda: tcp_check(8000))
    run_case("frontend_port_5173", lambda: tcp_check(5173))
    run_case(
        "mininet_topology_process",
        lambda: command_check(["pgrep", "-f", "[t]opology_hybrid_sdn.py"]),
    )
    run_case("ovs_core_hq", lambda: command_check(["ovs-vsctl", "br-exists", "core_hq"]))
    run_case("ovs_dist_branch", lambda: command_check(["ovs-vsctl", "br-exists", "dist_branch"]))
    run_case(
        "openflow_core_hq",
        lambda: command_check(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "core_hq"], contains="actions="),
    )
    run_case(
        "openflow_dist_branch",
        lambda: command_check(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "dist_branch"], contains="actions="),
    )
    run_case("api_health", health_case)
    run_case("agent_health_before", agent_health_case)

    ping_allow = {"source": "h30_01", "destination": "h90"}
    ping_deny = {"source": "h20_01", "destination": "h30_01"}
    udp_h90 = {"source": "h30_01", "destination": "h90", "protocol": "udp", "seconds": 5}
    tcp_h90 = {"source": "h30_01", "destination": "h90", "protocol": "tcp", "seconds": 5}
    quality_h90 = {"source": "h30_01", "destination": "h90", "protocol": "udp", "seconds": 5}

    run_case("ping_h30_to_voice", lambda: api_case(
        "/api/test/ping", ping_allow,
        lambda status, body: status == 200 and body.get("ok") is True,
    ))
    run_case("ping_project_isolation", lambda: api_case(
        "/api/test/ping", ping_deny,
        lambda status, body: (
            status == 200
            and body.get("ok") is False
            and body.get("error_code") == "POLICY_DENIED"
        ),
    ))
    run_case("udp_voice_first", lambda: api_case(
        "/api/test/iperf", udp_h90,
        lambda status, body: status == 200 and body.get("ok") is True,
    ))
    run_case("udp_voice_second", lambda: api_case(
        "/api/test/iperf", udp_h90,
        lambda status, body: status == 200 and body.get("ok") is True,
    ))
    run_case("tcp_voice", lambda: api_case(
        "/api/test/iperf", tcp_h90,
        lambda status, body: status == 200 and body.get("ok") is True,
    ))
    run_case("voice_quality", lambda: api_case(
        "/api/test/call-quality", quality_h90,
        lambda status, body: status == 200 and body.get("measurement_completed") is True,
        timeout=60,
    ))
    run_case("ping_after_iperf", lambda: api_case(
        "/api/test/ping", ping_allow,
        lambda status, body: status == 200 and body.get("ok") is True,
    ))
    run_case("agent_health_after", agent_health_case)

    run_case("concurrency_different_destinations", different_destination_concurrency_case)
    run_case("concurrency_same_destination_busy", same_destination_concurrency_case)

    run_case("runtime_logs_no_new_unhandled_errors", lambda: log_safety_case(offsets))
    save_report()
    return 0 if all(item["status"] == "PASS" for item in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
