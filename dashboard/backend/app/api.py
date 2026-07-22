from __future__ import annotations

import sqlite3
import time

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from . import auth_store, mininet_control
from .activity import activity_payload, append_event, record_operation, utc_now
from .errors import ApiError, ERROR_HTTP_STATUS
from .live_mininet import cluster_detail_test, current_metrics, enrich_decision, firewall_inventory, iperf_runtime_status, live_status, ovs_flows, pair_realtime_metrics, phase44_runtime_status, policy_decision, temporary_block
from .metrics import run_call_quality, run_iperf, run_ping
from .models import (
    ClusterTestRequest,
    HostPair,
    IperfRequest,
    LinkStateRequest,
    LinkUpdateRequest,
    LoginRequest,
    PasswordUpdateRequest,
    PolicyToggleRequest,
    RoleUpdateRequest,
    UserCreateRequest,
    UserStatusUpdateRequest,
)
from .policy import get_policy_payload, toggle_policy
from .security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    auth_status,
    cookie_secure,
    current_principal,
    require_admin,
    require_audit_reader,
    require_permission,
    require_operator,
)
from .topology import get_topology
from .runtime_health import live_health_payload, system_health


router = APIRouter(prefix="/api")
operator_required = Depends(require_operator)
dashboard_read_required = Depends(require_permission("dashboard.read"))


def _public_principal(principal: dict) -> dict:
    return {key: value for key, value in principal.items() if not key.startswith("_") and key != "permissions"}


def _set_session_cookies(response: Response, login_result: dict) -> None:
    max_age = auth_store.session_ttl_seconds()
    response.set_cookie(
        SESSION_COOKIE,
        login_result["token"],
        max_age=max_age,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        login_result["csrf_token"],
        max_age=max_age,
        httponly=False,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def _normalize_operation_error(payload: dict) -> dict:
    result = dict(payload)
    code = str(result.get("error_code") or "")
    infrastructure_codes = {
        "MININET_NOT_RUNNING",
        "AGENT_NOT_READY",
        "AGENT_TIMEOUT",
        "AGENT_DISCONNECTED",
        "CONTROLLER_OFFLINE",
        "OVS_UNAVAILABLE",
    }
    if (
        result.get("decision", {}).get("action") == "deny"
        and not result.get("ok")
        and code not in infrastructure_codes
    ):
        code = "POLICY_DENIED"
    elif code in {"IPERF_DESTINATION_BUSY", "IPERF_CONCURRENCY_LIMIT"}:
        code = "IPERF_BUSY"
    elif code in {"IPERF_SERVER_NOT_LISTENING", "IPERF_SERVER_START_FAILED"}:
        code = "IPERF_SERVER_FAILED"
    elif code in {"IPERF_CLIENT_ERROR"}:
        code = "IPERF_CLIENT_FAILED"
    elif code in {"IPERF_JSON_INVALID"} or result.get("parse_warning"):
        code = "IPERF_PARSE_FAILED"
    if code:
        result["error_code"] = code
    result.setdefault("message_vi", str(result.get("message") or "Tac vu hoan thanh."))
    return result


def operation_response(payload: dict) -> dict | JSONResponse:
    normalized = _normalize_operation_error(payload)
    code = str(normalized.get("error_code") or "")
    if normalized.get("ok") or normalized.get("measurement_completed") or code == "POLICY_DENIED":
        return normalized
    status_code = ERROR_HTTP_STATUS.get(code, 503)
    return JSONResponse(status_code=status_code, content=normalized)


def failed_link_ids() -> list[str]:
    status = mininet_control.get_link_status()
    if not status.get("ok"):
        return []
    return sorted(
        link_id
        for link_id, state in status.get("links", {}).items()
        if state == "down"
    )


def tracked_operation(
    *,
    user_action: str,
    event_type: str,
    component: str,
    source: str | None,
    destination: str | None,
    operation,
) -> dict:
    started_at = utc_now()
    started_monotonic = time.monotonic()
    payload = operation()
    return record_operation(
        user_action=user_action,
        event_type=event_type,
        component=component,
        source=source,
        destination=destination,
        started_at=started_at,
        started_monotonic=started_monotonic,
        payload=_normalize_operation_error(payload),
    )


@router.get("/topology")
def api_topology(principal: dict = Depends(require_permission("dashboard.read"))):
    return get_topology()


@router.get("/sites")
def api_sites(principal: dict = Depends(require_permission("dashboard.read"))):
    return {"sites": get_topology()["sites"]}


@router.get("/devices")
def api_devices(principal: dict = Depends(require_permission("dashboard.read"))):
    topology = get_topology()
    return {
        "devices": topology["devices"],
        "logical_switches": topology["logical_switches"],
        "runtime_bridge_map": topology["runtime_bridge_map"],
    }


@router.get("/firewalls")
def api_firewalls(principal: dict = Depends(require_permission("dashboard.read"))):
    return {
        "firewalls": firewall_inventory(),
        "phase44_runtime": phase44_runtime_status(),
    }


@router.get("/auth/status")
def api_auth_status():
    return auth_status()


@router.post("/auth/login")
def api_auth_login(payload: LoginRequest, request: Request, response: Response):
    result = auth_store.login(
        payload.username,
        payload.password,
        request_id=getattr(request.state, "request_id", None),
        source_ip=request.client.host if request.client else None,
    )
    if not result.get("ok"):
        code = str(result.get("error_code") or "AUTH_INVALID")
        status = 429 if code == "AUTH_LOCKED" else 401
        message = "Tài khoản đang tạm khóa do đăng nhập sai quá nhiều lần." if code == "AUTH_LOCKED" else "Tên đăng nhập hoặc mật khẩu không đúng."
        raise ApiError(status_code=status, error_code=code, message_vi=message)
    _set_session_cookies(response, result)
    return {"ok": True, "user": result["user"], "expires_at": result["expires_at"]}


@router.get("/auth/me")
def api_auth_me(principal: dict = Depends(current_principal)):
    return {"ok": True, "authenticated": True, "user": _public_principal(principal)}


@router.post("/auth/refresh")
def api_auth_refresh(request: Request, response: Response, principal: dict = Depends(current_principal)):
    token = principal.get("_session_token")
    if not token:
        return {"ok": True, "user": _public_principal(principal), "auth_method": "operator_token"}
    rotated = auth_store.rotate_session(
        token,
        request_id=getattr(request.state, "request_id", None),
        actor=principal,
        source_ip=request.client.host if request.client else None,
    )
    if not rotated:
        raise ApiError(status_code=401, error_code="AUTH_EXPIRED", message_vi="Phiên đăng nhập đã hết hạn.")
    _set_session_cookies(response, rotated)
    return {"ok": True, "user": rotated["user"], "expires_at": rotated["expires_at"]}


@router.post("/auth/logout")
def api_auth_logout(request: Request, response: Response, principal: dict = Depends(current_principal)):
    from .security import csrf_check

    csrf_check(request, principal)
    auth_store.revoke_session(
        request.cookies.get(SESSION_COOKIE),
        request_id=getattr(request.state, "request_id", None),
        actor=principal,
        source_ip=request.client.host if request.client else None,
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True, "message_vi": "Đã đăng xuất phiên hiện tại."}


@router.get("/auth/verify")
def api_auth_verify(principal: dict = Depends(require_operator)):
    append_event(component="backend", event_type="auth", message="Xác thực IT Operator thành công.", severity="info")
    return {"ok": True, "authenticated": True, "role": principal.get("role"), "auth_method": principal.get("auth_method")}


@router.get("/admin/users")
def api_admin_users(principal: dict = Depends(require_admin)):
    return {"users": auth_store.list_users()}


@router.post("/admin/users")
def api_admin_create_user(payload: UserCreateRequest, request: Request, principal: dict = Depends(require_admin)):
    try:
        user = auth_store.create_user(payload.username, payload.password, payload.role)
    except sqlite3.IntegrityError:
        raise ApiError(status_code=409, error_code="USER_EXISTS", message_vi="Username đã tồn tại.") from None
    except ValueError as exc:
        raise ApiError(status_code=422, error_code="VALIDATION_ERROR", message_vi=str(exc)) from exc
    auth_store.audit(action="user.create", result="success", request_id=getattr(request.state, "request_id", None), actor=principal, source_ip=request.client.host if request.client else None, detail={"username": user["username"], "role": user["role"]})
    return {"ok": True, "user": user}


@router.patch("/admin/users/{username}/role")
def api_admin_update_role(username: str, payload: RoleUpdateRequest, request: Request, principal: dict = Depends(require_admin)):
    try:
        user = auth_store.update_role(username, payload.role)
    except (KeyError, ValueError) as exc:
        raise ApiError(status_code=404, error_code="USER_NOT_FOUND", message_vi=str(exc)) from exc
    auth_store.audit(action="user.role_change", result="success", request_id=getattr(request.state, "request_id", None), actor=principal, source_ip=request.client.host if request.client else None, detail={"username": username, "role": payload.role})
    return {"ok": True, "user": user}


@router.patch("/admin/users/{username}/password")
def api_admin_update_password(username: str, payload: PasswordUpdateRequest, request: Request, principal: dict = Depends(require_admin)):
    try:
        user = auth_store.change_password(username, payload.password)
    except (KeyError, ValueError) as exc:
        raise ApiError(status_code=404, error_code="USER_NOT_FOUND", message_vi=str(exc)) from exc
    auth_store.audit(action="user.password_change", result="success", request_id=getattr(request.state, "request_id", None), actor=principal, source_ip=request.client.host if request.client else None, detail={"username": username})
    return {"ok": True, "user": user}


@router.patch("/admin/users/{username}/status")
def api_admin_update_status(username: str, payload: UserStatusUpdateRequest, request: Request, principal: dict = Depends(require_admin)):
    try:
        user = auth_store.set_disabled(username, payload.disabled)
    except (KeyError, ValueError) as exc:
        raise ApiError(status_code=404, error_code="USER_NOT_FOUND", message_vi=str(exc)) from exc
    auth_store.audit(action="user.status_change", result="success", request_id=getattr(request.state, "request_id", None), actor=principal, source_ip=request.client.host if request.client else None, detail={"username": username, "disabled": payload.disabled})
    return {"ok": True, "user": user}


@router.get("/admin/audit")
def api_admin_audit(limit: int = 200, principal: dict = Depends(require_audit_reader)):
    return {"events": auth_store.audit_events(limit)}


@router.get("/policies")
def api_policies(principal: dict = Depends(require_permission("dashboard.read"))):
    return get_policy_payload()


@router.get("/flows")
def api_flows(request: Request, principal: dict = Depends(require_permission("dashboard.read"))):
    return ovs_flows()


@router.get("/metrics/current")
def api_metrics_current(request: Request, principal: dict = Depends(require_permission("dashboard.read"))):
    return current_metrics()


@router.post("/metrics/pair", dependencies=[operator_required])
def api_metrics_pair(payload: HostPair):
    return pair_realtime_metrics(payload.source, payload.destination)


@router.get("/live/status")
def api_live_status(principal: dict = Depends(require_permission("dashboard.read"))):
    return {
        **live_health_payload(),
        "iperf_sessions": iperf_runtime_status(),
        "firewalls": firewall_inventory(),
        "phase44_runtime": phase44_runtime_status(),
    }


@router.get("/live/iperf-sessions", dependencies=[operator_required])
def api_live_iperf_sessions():
    return iperf_runtime_status()


@router.get("/health")
def api_health():
    return system_health()


@router.get("/activity", dependencies=[operator_required])
def api_activity(limit: int = 300):
    return activity_payload(limit)


@router.post("/test/ping", dependencies=[operator_required])
def api_test_ping(payload: HostPair):
    result = tracked_operation(
        user_action="Ping",
        event_type="ping",
        component="mininet_control_agent",
        source=payload.source,
        destination=payload.destination,
        operation=lambda: run_ping(payload.source, payload.destination),
    )
    return operation_response(result)


@router.post("/test/iperf", dependencies=[operator_required])
def api_test_iperf(payload: IperfRequest):
    result = tracked_operation(
        user_action=f"iperf {payload.protocol.upper()}",
        event_type="iperf",
        component="mininet_control_agent",
        source=payload.source,
        destination=payload.destination,
        operation=lambda: run_iperf(payload.source, payload.destination, payload.protocol, payload.seconds),
    )
    return operation_response(result)


@router.post("/test/call-quality", dependencies=[operator_required])
def api_test_call_quality(payload: IperfRequest):
    result = tracked_operation(
        user_action="Voice Quality",
        event_type="voice_quality",
        component="mininet_control_agent",
        source=payload.source,
        destination=payload.destination,
        operation=lambda: run_call_quality(payload.source, payload.destination, payload.seconds),
    )
    return operation_response(result)


@router.post("/test/cluster-detail", dependencies=[operator_required])
def api_test_cluster_detail(payload: ClusterTestRequest):
    return cluster_detail_test(payload.cluster, payload.seconds)


@router.post("/live/block", dependencies=[operator_required])
def api_live_block(payload: HostPair):
    return tracked_operation(
        user_action="Manual block",
        event_type="manual_flow",
        component="openvswitch",
        source=payload.source,
        destination=payload.destination,
        operation=lambda: temporary_block(payload.source, payload.destination, block=True),
    )


@router.post("/live/unblock", dependencies=[operator_required])
def api_live_unblock(payload: HostPair):
    return tracked_operation(
        user_action="Manual unblock",
        event_type="manual_flow",
        component="openvswitch",
        source=payload.source,
        destination=payload.destination,
        operation=lambda: temporary_block(payload.source, payload.destination, block=False),
    )


@router.post("/policy/apply", dependencies=[operator_required])
def api_policy_apply():
    return {"ok": False, "message": "Dung /api/policy/toggle de ghi policy.yml atomic va yeu cau controller reload."}


@router.post("/policy/toggle", dependencies=[operator_required])
def api_policy_toggle(payload: PolicyToggleRequest):
    started_at = utc_now()
    started_monotonic = time.monotonic()
    try:
        result = toggle_policy(payload.key, payload.enabled)
    except (KeyError, ValueError) as exc:
        result = {"ok": False, "message": str(exc), "error_code": "POLICY_APPLY_FAILED"}
    return record_operation(
        user_action=f"{'Bật' if payload.enabled else 'Tắt'} policy {payload.key}",
        event_type="policy",
        component="controller",
        source=payload.key,
        destination=None,
        started_at=started_at,
        started_monotonic=started_monotonic,
        payload=_normalize_operation_error(result),
    )


@router.post("/simulate/path", dependencies=[operator_required])
def api_simulate_path(payload: HostPair):
    decision = policy_decision(payload.source, payload.destination)
    path = decision.get("path", [])
    down = mininet_control.first_down_link(path)
    if down:
        failed_link = down["link_id"]
        blocked_at = down["blocked_at"]
        stop_index = path.index(blocked_at) if blocked_at in path else 0
        decision = {
            **decision,
            "action": "deny",
            "reason": "Khong co duong di hop le do lien ket that trong Mininet dang down.",
            "path": path[: stop_index + 1],
            "blocked_at": blocked_at,
            "failed_link": failed_link,
        }
        return {
            "src": payload.source,
            "dst": payload.destination,
            **enrich_decision(payload.source, payload.destination, decision),
            "mode": "logical_architecture",
        }
    return {
        "src": payload.source,
        "dst": payload.destination,
        **enrich_decision(payload.source, payload.destination, decision),
        "mode": "logical_architecture",
        "note": "Duong logic phuc vu minh hoa; ket qua ping/iperf van lay truc tiep tu Mininet/OVS.",
    }


@router.post("/link/update", dependencies=[operator_required])
def api_link_update(payload: LinkUpdateRequest):
    return {"ok": True, "message": "Co the thay doi bandwidth/delay/loss bang TCLink trong Mininet.", "link": payload.model_dump()}


@router.post("/link/fail", dependencies=[operator_required])
def api_link_fail(payload: LinkStateRequest):
    def operation():
        result = mininet_control.set_link_state(payload.link_id, "down")
        result["failed_links"] = failed_link_ids()
        return result
    return tracked_operation(
        user_action=f"Fail link {payload.link_id}",
        event_type="link",
        component="mininet_control_agent",
        source=payload.link_id,
        destination=None,
        operation=operation,
    )


@router.post("/link/recover", dependencies=[operator_required])
def api_link_recover(payload: LinkStateRequest):
    def operation():
        result = mininet_control.set_link_state(payload.link_id, "up")
        result["failed_links"] = failed_link_ids()
        return result
    return tracked_operation(
        user_action=f"Recover link {payload.link_id}",
        event_type="link",
        component="mininet_control_agent",
        source=payload.link_id,
        destination=None,
        operation=operation,
    )
