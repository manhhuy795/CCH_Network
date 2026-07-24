#!/usr/bin/env python3
"""Kiểm thử runtime chi tiết cho health, auth/RBAC và audit event Phase 49.

Script chỉ gọi API/runtime thật của dashboard đang chạy. Token máy chỉ được
đọc từ logs/operator.token và không bao giờ được ghi vào console/report.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("CCH_DASHBOARD_URL", "http://127.0.0.1:8000").rstrip("/")
PYTHON = sys.executable


@dataclass
class HttpResult:
    status: int
    payload: dict[str, Any]
    duration_ms: float
    transport_error: str | None = None


class ApiSession:
    def __init__(self) -> None:
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30,
    ) -> HttpResult:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = {"Accept": "application/json"}
        if body is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        request = Request(f"{BASE_URL}{path}", data=body, headers=request_headers, method=method)
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                status = response.status
        except HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            status = error.code
        except (URLError, TimeoutError, OSError) as error:
            return HttpResult(0, {}, (time.monotonic() - started) * 1000, str(error))
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"_malformed": True}
        return HttpResult(status, parsed if isinstance(parsed, dict) else {}, (time.monotonic() - started) * 1000)

    def csrf(self) -> str:
        for cookie in self.cookies:
            if cookie.name == "cch_csrf":
                return cookie.value
        raise RuntimeError("CSRF cookie không tồn tại sau đăng nhập")


class DetailedRuntimeTest:
    def __init__(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.report_dir = ROOT / "runtime_reports" / f"phase49_detailed_status_events_{timestamp}"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.results: list[dict[str, Any]] = []
        self.log_lines: list[str] = []
        self.operator_token = self._read_operator_token()
        self.admin = ApiSession()
        self.viewer = ApiSession()
        self.human_operator = ApiSession()
        self.auditor = ApiSession()
        run_id = f"{int(time.time())}_{os.getpid()}"
        self.admin_user = f"p49a_{run_id}"
        self.viewer_user = f"p49v_{run_id}"
        self.operator_user = f"p49o_{run_id}"
        self.auditor_user = f"p49r_{run_id}"
        self.admin_password = secrets.token_urlsafe(24)
        self.viewer_password = secrets.token_urlsafe(24)
        self.operator_password = secrets.token_urlsafe(24)
        self.auditor_password = secrets.token_urlsafe(24)

    def _read_operator_token(self) -> str:
        token_path = ROOT / "logs" / "operator.token"
        token = token_path.read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError(f"Không đọc được operator token từ {token_path}")
        return token

    def log(self, line: str) -> None:
        print(line, flush=True)
        self.log_lines.append(line)

    @staticmethod
    def _response_summary(response: HttpResult) -> dict[str, Any]:
        payload = response.payload
        summary: dict[str, Any] = {
            "http_status": response.status,
            "duration_ms": round(response.duration_ms, 2),
        }
        if response.transport_error:
            summary["transport_error"] = response.transport_error
            return summary
        for key in ("ok", "authenticated", "error_code", "action", "auth_method", "role"):
            if key in payload:
                summary[key] = payload[key]
        if isinstance(payload.get("user"), dict):
            summary["user_role"] = payload["user"].get("role")
        if isinstance(payload.get("decision"), dict):
            summary["action"] = payload["decision"].get("action")
        if isinstance(payload.get("result"), dict):
            for key in ("throughput_mbps", "jitter_ms", "packet_loss_percent", "measurement_completed"):
                if key in payload["result"]:
                    summary[key] = payload["result"][key]
        if isinstance(payload.get("components"), dict):
            summary["components"] = {
                name: item.get("status")
                for name, item in payload["components"].items()
                if isinstance(item, dict)
            }
        if isinstance(payload.get("events"), list):
            summary["event_count"] = len(payload["events"])
        if isinstance(payload.get("users"), list):
            summary["user_count"] = len(payload["users"])
        return summary

    def case(self, name: str, function: Callable[[], tuple[bool, dict[str, Any]]]) -> bool:
        started = time.monotonic()
        try:
            passed, details = function()
        except Exception as error:  # pragma: no cover - runtime failure path
            passed = False
            details = {"error_code": "SCRIPT_ERROR", "detail": str(error)}
        details = {**details, "duration_ms": round((time.monotonic() - started) * 1000, 2)}
        result = {"case": name, "status": "PASS" if passed else "FAIL", **details}
        self.results.append(result)
        self.log(f"{result['status']:<4} {name}: {json.dumps(details, ensure_ascii=False, sort_keys=True)}")
        return passed

    def expect_http(
        self,
        session: ApiSession,
        method: str,
        path: str,
        expected_status: int,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        predicate: Callable[[dict[str, Any]], bool] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        response = session.request(method, path, payload=payload, headers=headers)
        passed = response.status == expected_status and response.transport_error is None
        if predicate is not None:
            passed = passed and predicate(response.payload)
        summary = self._response_summary(response)
        if not passed and response.status == expected_status and response.payload.get("_malformed"):
            summary["error_code"] = "MALFORMED_JSON"
        return passed, summary

    def command(self, args: list[str], *, sudo: bool = False, input_text: str | None = None, timeout: float = 20) -> subprocess.CompletedProcess[str]:
        command = (["sudo", "-n"] if sudo else []) + args
        return subprocess.run(command, cwd=ROOT, input=input_text, capture_output=True, text=True, timeout=timeout, check=False)

    def bootstrap(self, username: str, password: str) -> tuple[bool, dict[str, Any]]:
        result = self.command(
            [PYTHON, "scripts/phase49_bootstrap_admin.py", "--username", username, "--password-stdin"],
            input_text=f"{password}\n",
        )
        return result.returncode == 0, {"exit_code": result.returncode, "username": username}

    @staticmethod
    def role_is(payload: dict[str, Any], role: str) -> bool:
        user = payload.get("user")
        return isinstance(user, dict) and user.get("role") == role

    def admin_csrf_headers(self) -> dict[str, str]:
        return {"X-CCH-CSRF": self.admin.csrf()}

    def run(self) -> int:
        self.log("Phase 49 detailed status/event runtime test")
        self.log(f"Dashboard: {BASE_URL}")
        self.case("linux_runtime", lambda: (sys.platform == "linux", {"platform": sys.platform}))
        self.case("required_commands", self.check_commands)
        self.case("required_ports", self.check_ports)
        self.case("health_components", self.check_health)
        self.case("operator_token_file", lambda: (bool(self.operator_token), {"present": True}))
        self.case("ovs_bridges", self.check_ovs)
        self.case("core_openflow_inventory", self.check_core_flows)

        operator_headers = {"X-CCH-Operator-Token": self.operator_token}
        self.case("unauthenticated_me", lambda: self.expect_http(ApiSession(), "GET", "/api/auth/me", 401, predicate=lambda p: p.get("error_code") == "AUTH_REQUIRED"))
        self.case("unauthenticated_topology", lambda: self.expect_http(ApiSession(), "GET", "/api/topology", 401, predicate=lambda p: p.get("error_code") == "AUTH_REQUIRED"))
        self.case("operator_verify", lambda: self.expect_http(ApiSession(), "GET", "/api/auth/verify", 200, headers=operator_headers, predicate=lambda p: p.get("auth_method") == "operator_token" and p.get("role") == "operator"))
        self.case("operator_live_status", lambda: self.expect_http(ApiSession(), "GET", "/api/live/status", 200, headers=operator_headers, predicate=self.status_payload_is_valid))
        self.case("operator_topology", lambda: self.expect_http(ApiSession(), "GET", "/api/topology", 200, headers=operator_headers, predicate=lambda p: bool(p.get("nodes"))))
        self.case("operator_flows", lambda: self.expect_http(ApiSession(), "GET", "/api/flows", 200, headers=operator_headers, predicate=lambda p: bool(p.get("flows"))))
        self.case("operator_ping_allow", lambda: self.expect_http(ApiSession(), "POST", "/api/test/ping", 200, headers={**operator_headers, "Content-Type": "application/json"}, payload={"source": "h30_01", "destination": "h90"}, predicate=lambda p: p.get("ok") is True and p.get("decision", {}).get("action") == "allow"))
        self.case("operator_ping_policy_deny", lambda: self.expect_http(ApiSession(), "POST", "/api/test/ping", 200, headers={**operator_headers, "Content-Type": "application/json"}, payload={"source": "h20_01", "destination": "h30_01"}, predicate=lambda p: p.get("ok") is False and p.get("decision", {}).get("action") == "deny" and p.get("error_code") == "POLICY_DENIED"))
        self.case("operator_token_not_admin", lambda: self.expect_http(ApiSession(), "GET", "/api/admin/users", 403, headers=operator_headers, predicate=lambda p: p.get("error_code") == "RBAC_FORBIDDEN"))

        self.case("bootstrap_admin", lambda: self.bootstrap(self.admin_user, self.admin_password))
        self.case("admin_login", lambda: self.expect_http(self.admin, "POST", "/api/auth/login", 200, payload={"username": self.admin_user, "password": self.admin_password}, predicate=lambda p: p.get("ok") is True and self.role_is(p, "admin")))
        self.case("admin_me", lambda: self.expect_http(self.admin, "GET", "/api/auth/me", 200, predicate=lambda p: p.get("authenticated") is True and self.role_is(p, "admin")))
        self.case("invalid_password", lambda: self.expect_http(ApiSession(), "POST", "/api/auth/login", 401, payload={"username": self.admin_user, "password": "wrong-password"}, predicate=lambda p: p.get("error_code") == "AUTH_INVALID"))
        self.case("admin_users_list", lambda: self.expect_http(self.admin, "GET", "/api/admin/users", 200, headers=self.admin_csrf_headers(), predicate=lambda p: any(item.get("username") == self.admin_user and item.get("role") == "admin" for item in p.get("users", []))))

        self.case("create_viewer", lambda: self.create_user(self.viewer_user, self.viewer_password, "viewer"))
        self.case("create_human_operator", lambda: self.create_user(self.operator_user, self.operator_password, "operator"))
        self.case("create_auditor", lambda: self.create_user(self.auditor_user, self.auditor_password, "auditor"))
        self.case("viewer_login", lambda: self.expect_http(self.viewer, "POST", "/api/auth/login", 200, payload={"username": self.viewer_user, "password": self.viewer_password}, predicate=lambda p: self.role_is(p, "viewer")))
        self.case("viewer_me", lambda: self.expect_http(self.viewer, "GET", "/api/auth/me", 200, predicate=lambda p: self.role_is(p, "viewer")))
        self.case("viewer_runtime_forbidden", lambda: self.expect_http(self.viewer, "POST", "/api/test/ping", 403, payload={"source": "h30_01", "destination": "h90"}, headers={"X-CCH-CSRF": self.viewer.csrf()}, predicate=lambda p: p.get("error_code") == "RBAC_FORBIDDEN"))
        self.case("viewer_admin_forbidden", lambda: self.expect_http(self.viewer, "GET", "/api/admin/users", 403, headers={"X-CCH-CSRF": self.viewer.csrf()}, predicate=lambda p: p.get("error_code") == "RBAC_FORBIDDEN"))
        self.case("viewer_audit_forbidden", lambda: self.expect_http(self.viewer, "GET", "/api/admin/audit", 403, predicate=lambda p: p.get("error_code") == "RBAC_FORBIDDEN"))

        self.case("disable_viewer", lambda: self.update_user_status(self.viewer_user, True))
        self.case("disabled_login_rejected", lambda: self.expect_http(ApiSession(), "POST", "/api/auth/login", 401, payload={"username": self.viewer_user, "password": self.viewer_password}, predicate=lambda p: p.get("error_code") == "AUTH_INVALID"))
        self.case("reenable_viewer", lambda: self.update_user_status(self.viewer_user, False))
        self.case("change_viewer_role_to_auditor", lambda: self.update_user_role(self.viewer_user, "auditor"))
        self.case("human_operator_login", lambda: self.expect_http(self.human_operator, "POST", "/api/auth/login", 200, payload={"username": self.operator_user, "password": self.operator_password}, predicate=lambda p: self.role_is(p, "operator")))
        self.case("human_operator_runtime_allowed", lambda: self.expect_http(self.human_operator, "POST", "/api/test/ping", 200, payload={"source": "h30_01", "destination": "h90"}, headers={"X-CCH-CSRF": self.human_operator.csrf()}, predicate=lambda p: p.get("decision", {}).get("action") == "allow"))
        self.case("human_operator_admin_forbidden", lambda: self.expect_http(self.human_operator, "GET", "/api/admin/users", 403, headers={"X-CCH-CSRF": self.human_operator.csrf()}, predicate=lambda p: p.get("error_code") == "RBAC_FORBIDDEN"))
        self.case("auditor_login", lambda: self.expect_http(self.auditor, "POST", "/api/auth/login", 200, payload={"username": self.auditor_user, "password": self.auditor_password}, predicate=lambda p: self.role_is(p, "auditor")))
        self.case("auditor_can_read_audit", lambda: self.expect_http(self.auditor, "GET", "/api/admin/audit?limit=200", 200, predicate=lambda p: len(p.get("events", [])) > 0 and self.audit_has_no_secrets(p)))
        self.case("auditor_runtime_forbidden", lambda: self.expect_http(self.auditor, "POST", "/api/test/ping", 403, payload={"source": "h30_01", "destination": "h90"}, headers={"X-CCH-CSRF": self.auditor.csrf()}, predicate=lambda p: p.get("error_code") == "RBAC_FORBIDDEN"))
        self.case("admin_refresh_session", lambda: self.expect_http(self.admin, "POST", "/api/auth/refresh", 200, headers=self.admin_csrf_headers(), predicate=lambda p: p.get("ok") is True))
        self.case("audit_event_history", lambda: self.expect_http(self.admin, "GET", "/api/admin/audit?limit=200", 200, predicate=lambda p: self.audit_contains_expected_events(p)))
        self.case("operator_activity_events", lambda: self.expect_http(self.human_operator, "GET", "/api/activity", 200, headers={"X-CCH-CSRF": self.human_operator.csrf()}, predicate=lambda p: isinstance(p.get("events"), list) or isinstance(p.get("activity"), list)))
        self.case("admin_logout", lambda: self.expect_http(self.admin, "POST", "/api/auth/logout", 200, headers=self.admin_csrf_headers(), predicate=lambda p: p.get("ok") is True))
        self.case("admin_me_after_logout", lambda: self.expect_http(self.admin, "GET", "/api/auth/me", 401, predicate=lambda p: p.get("error_code") == "AUTH_REQUIRED"))
        self.case("health_after_security_tests", self.check_health)
        return self.finish()

    def check_commands(self) -> tuple[bool, dict[str, Any]]:
        names = ["curl", "ss", "python3"]
        missing = [name for name in names if self.command(["bash", "-lc", f"command -v {name}"]).returncode != 0]
        return not missing, {"missing": missing}

    def check_ports(self) -> tuple[bool, dict[str, Any]]:
        ports = {"controller": 6653, "backend": 8000, "frontend": 5173}
        closed = []
        for name, port in ports.items():
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=2):
                    pass
            except OSError:
                closed.append(name)
        return not closed, {"ports": ports, "closed": closed}

    def check_health(self) -> tuple[bool, dict[str, Any]]:
        response = ApiSession().request("GET", "/api/health")
        required = ("backend", "frontend", "controller", "mininet_topology", "mininet_control_agent", "openvswitch", "websocket", "flow_inventory")
        statuses = {name: response.payload.get("components", {}).get(name, {}).get("status") for name in required}
        passed = response.status == 200 and all(statuses[name] == "online" for name in required if name != "websocket") and statuses["websocket"] in {"online", "unknown"}
        return passed, {"http_status": response.status, "system_status": response.payload.get("system_status"), "components": statuses}

    def check_ovs(self) -> tuple[bool, dict[str, Any]]:
        result = self.command(["ovs-vsctl", "list-br"], sudo=True)
        bridges = result.stdout.split()
        required = {"core_hq", "dist_branch", "access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2", "access_branch", "infra_access"}
        return result.returncode == 0 and required.issubset(bridges), {"exit_code": result.returncode, "bridge_count": len(bridges), "missing": sorted(required - set(bridges))}

    def check_core_flows(self) -> tuple[bool, dict[str, Any]]:
        result = self.command(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "core_hq"], sudo=True)
        flow_lines = [line for line in result.stdout.splitlines() if "cookie=" in line and "priority=" in line]
        return result.returncode == 0 and bool(flow_lines), {"exit_code": result.returncode, "flow_count": len(flow_lines), "runtime_evidence": bool(flow_lines)}

    def status_payload_is_valid(self, payload: dict[str, Any]) -> bool:
        components = payload.get("components", {})
        allowed = {"online", "offline", "degraded", "unknown"}
        required = ("backend", "frontend", "controller", "mininet_topology", "mininet_control_agent", "openvswitch", "websocket", "flow_inventory")
        return all(name in components and components[name].get("status") in allowed for name in required)

    def create_user(self, username: str, password: str, role: str) -> tuple[bool, dict[str, Any]]:
        response = self.admin.request("POST", "/api/admin/users", payload={"username": username, "password": password, "role": role}, headers=self.admin_csrf_headers())
        return response.status == 200 and response.payload.get("user", {}).get("role") == role, self._response_summary(response)

    def update_user_status(self, username: str, disabled: bool) -> tuple[bool, dict[str, Any]]:
        response = self.admin.request("PATCH", f"/api/admin/users/{username}/status", payload={"disabled": disabled}, headers=self.admin_csrf_headers())
        return response.status == 200 and response.payload.get("user", {}).get("disabled") is disabled, self._response_summary(response)

    def update_user_role(self, username: str, role: str) -> tuple[bool, dict[str, Any]]:
        response = self.admin.request("PATCH", f"/api/admin/users/{username}/role", payload={"role": role}, headers=self.admin_csrf_headers())
        return response.status == 200 and response.payload.get("user", {}).get("role") == role, self._response_summary(response)

    def audit_has_no_secrets(self, payload: dict[str, Any]) -> bool:
        text = json.dumps(payload, ensure_ascii=False)
        return all(secret not in text for secret in (self.operator_token, self.admin_password, self.viewer_password, self.operator_password, self.auditor_password))

    def audit_contains_expected_events(self, payload: dict[str, Any]) -> bool:
        events = payload.get("events", [])
        actions = {event.get("action") for event in events if isinstance(event, dict)}
        return len(events) > 0 and {"login", "user.create", "user.status_change", "user.role_change"}.issubset(actions) and self.audit_has_no_secrets(payload)

    def finish(self) -> int:
        failed = [item for item in self.results if item["status"] != "PASS"]
        summary = {
            "phase": 49,
            "suite": "detailed_status_and_events",
            "base_url": BASE_URL,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": "PASS" if not failed else "FAIL",
            "case_counts": {status: sum(item["status"] == status for item in self.results) for status in ("PASS", "FAIL")},
            "cases": self.results,
            "secret_policy": "operator token and test passwords are never written to report",
        }
        json_path = self.report_dir / "summary.json"
        log_path = self.report_dir / "runtime.log"
        json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        log_path.write_text("\n".join(self.log_lines) + "\n", encoding="utf-8")
        report_text = json_path.read_text(encoding="utf-8") + log_path.read_text(encoding="utf-8")
        if self.operator_token in report_text or any(password in report_text for password in (self.admin_password, self.viewer_password, self.operator_password, self.auditor_password)):
            self.log("FAIL secret_safety_report_check: sensitive value would be written")
            return 1
        self.log(f"RESULT {len(self.results) - len(failed)}/{len(self.results)} PASS")
        self.log(f"ARTIFACT JSON={json_path}")
        self.log(f"ARTIFACT LOG={log_path}")
        return 0 if not failed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(DetailedRuntimeTest().run())
    except Exception as error:
        print(f"FAIL phase49_detailed_status_event_test: {error}", file=sys.stderr)
        raise SystemExit(1)
