from __future__ import annotations

import os
import secrets
from typing import Any, Callable

from fastapi import Depends, Header, Request

from . import auth_store
from .activity import append_event
from .errors import ApiError


OPERATOR_TOKEN_ENV = "CCH_DASHBOARD_OPERATOR_TOKEN"
CORS_ORIGINS_ENV = "CCH_DASHBOARD_CORS_ORIGINS"
COOKIE_SECURE_ENV = "CCH_AUTH_COOKIE_SECURE"
SESSION_COOKIE = "cch_session"
CSRF_COOKIE = "cch_csrf"
CSRF_HEADER = "X-CCH-CSRF"
DEFAULT_CORS_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")
DEFAULT_CORS_ORIGIN_REGEX = (
    r"^http://("
    r"localhost|127\.0\.0\.1|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"192\.168\.\d{1,3}\.\d{1,3}|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
    r"):5173$"
)


def configured_operator_token() -> str:
    return os.environ.get(OPERATOR_TOKEN_ENV, "").strip()


def cookie_secure() -> bool:
    value = os.environ.get(COOKIE_SECURE_ENV, "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def cors_origins() -> list[str]:
    configured = os.environ.get(CORS_ORIGINS_ENV, "").strip()
    if not configured:
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]


def cors_origin_regex() -> str:
    return os.environ.get("CCH_DASHBOARD_CORS_ORIGIN_REGEX", DEFAULT_CORS_ORIGIN_REGEX)


def auth_status() -> dict[str, object]:
    return {
        "human_auth_enabled": True,
        "session_cookie": SESSION_COOKIE,
        "csrf_header": CSRF_HEADER,
        "session_ttl_seconds": auth_store.session_ttl_seconds(),
        "roles": list(auth_store.ROLES),
        "operator_auth_required": True,
        "operator_token_configured": bool(configured_operator_token()),
        "operator_token_header": "X-CCH-Operator-Token",
        "operator_token_exposure": "backend_and_runtime_scripts_only",
    }


def _source_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _operator_principal(request: Request) -> dict[str, Any] | None:
    expected = configured_operator_token()
    if not expected:
        return None
    provided = request.headers.get("X-CCH-Operator-Token", "").strip()
    if not provided:
        authorization = request.headers.get("Authorization", "")
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            provided = value.strip()
    if provided and secrets.compare_digest(provided, expected):
        return {
            "id": "operator-token",
            "username": "operator-token",
            "role": "operator",
            "permissions": sorted(auth_store.ROLE_PERMISSIONS["operator"]),
            "auth_method": "operator_token",
        }
    if provided:
        append_event(component="backend", event_type="auth", message="Xác thực operator token thất bại.", severity="warning", error_code="AUTH_INVALID")
        raise ApiError(status_code=403, error_code="AUTH_INVALID", message_vi="Operator token không hợp lệ.")
    return None


def current_principal(request: Request) -> dict[str, Any]:
    operator = _operator_principal(request)
    if operator:
        return operator
    session = auth_store.session_principal(request.cookies.get(SESSION_COOKIE))
    if session:
        return session
    append_event(component="backend", event_type="auth", message="Yêu cầu chưa xác thực.", severity="warning", error_code="AUTH_REQUIRED")
    raise ApiError(status_code=401, error_code="AUTH_REQUIRED", message_vi="Cần đăng nhập để thực hiện thao tác này.")


def csrf_check(request: Request, principal: dict[str, Any]) -> None:
    if principal.get("auth_method") == "operator_token":
        return
    cookie = request.cookies.get(CSRF_COOKIE, "")
    supplied = request.headers.get(CSRF_HEADER, "")
    if not cookie or not supplied or not secrets.compare_digest(cookie, supplied):
        auth_store.audit(
            action="csrf_check",
            result="denied",
            request_id=getattr(request.state, "request_id", None),
            actor=principal,
            source_ip=_source_ip(request),
        )
        raise ApiError(status_code=403, error_code="CSRF_INVALID", message_vi="Yêu cầu CSRF không hợp lệ.")


def require_permission(permission: str, *, write: bool = False) -> Callable[..., dict[str, Any]]:
    def dependency(request: Request, principal: dict[str, Any] = Depends(current_principal)) -> dict[str, Any]:
        if write:
            csrf_check(request, principal)
        if not auth_store.has_permission(principal, permission):
            auth_store.audit(
                action=f"rbac:{permission}",
                result="denied",
                request_id=getattr(request.state, "request_id", None),
                actor=principal,
                source_ip=_source_ip(request),
            )
            raise ApiError(status_code=403, error_code="RBAC_FORBIDDEN", message_vi="Tài khoản không có quyền thực hiện thao tác này.")
        return principal

    return dependency


def require_operator(request: Request, principal: dict[str, Any] = Depends(current_principal)) -> dict[str, Any]:
    csrf_check(request, principal)
    if not auth_store.has_permission(principal, "runtime.execute"):
        auth_store.audit(
            action="runtime.execute",
            result="denied",
            request_id=getattr(request.state, "request_id", None),
            actor=principal,
            source_ip=_source_ip(request),
        )
        raise ApiError(status_code=403, error_code="RBAC_FORBIDDEN", message_vi="Chỉ operator hoặc admin được thực hiện thao tác runtime.")
    return principal


def require_admin(request: Request, principal: dict[str, Any] = Depends(current_principal)) -> dict[str, Any]:
    csrf_check(request, principal)
    if principal.get("role") != "admin":
        auth_store.audit(
            action="admin.access",
            result="denied",
            request_id=getattr(request.state, "request_id", None),
            actor=principal,
            source_ip=_source_ip(request),
        )
        raise ApiError(status_code=403, error_code="RBAC_FORBIDDEN", message_vi="Chỉ admin được quản lý user và role.")
    return principal


def require_audit_reader(request: Request, principal: dict[str, Any] = Depends(current_principal)) -> dict[str, Any]:
    if not auth_store.has_permission(principal, "audit.read") and principal.get("role") not in {"admin", "operator"}:
        raise ApiError(status_code=403, error_code="RBAC_FORBIDDEN", message_vi="Tài khoản không có quyền xem nhật ký audit.")
    return principal


def websocket_principal(websocket: Any) -> dict[str, Any] | None:
    expected = configured_operator_token()
    provided = websocket.headers.get("X-CCH-Operator-Token", "").strip()
    if expected and provided and secrets.compare_digest(provided, expected):
        return {
            "id": "operator-token",
            "username": "operator-token",
            "role": "operator",
            "permissions": sorted(auth_store.ROLE_PERMISSIONS["operator"]),
            "auth_method": "operator_token",
        }
    return auth_store.session_principal(websocket.cookies.get(SESSION_COOKIE))
