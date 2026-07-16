from __future__ import annotations

import os
import secrets

from fastapi import Header

from .activity import append_event
from .errors import ApiError


TOKEN_ENV = "CCH_DASHBOARD_OPERATOR_TOKEN"
CORS_ORIGINS_ENV = "CCH_DASHBOARD_CORS_ORIGINS"
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
    return os.environ.get(TOKEN_ENV, "").strip()


def auth_status() -> dict[str, object]:
    return {
        "operator_auth_required": True,
        "operator_token_configured": bool(configured_operator_token()),
        "token_header": "X-CCH-Operator-Token",
        "role": "it_operator",
    }


def cors_origins() -> list[str]:
    configured = os.environ.get(CORS_ORIGINS_ENV, "").strip()
    if not configured:
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]


def cors_origin_regex() -> str:
    return os.environ.get("CCH_DASHBOARD_CORS_ORIGIN_REGEX", DEFAULT_CORS_ORIGIN_REGEX)


def require_operator(
    x_cch_operator_token: str | None = Header(default=None, alias="X-CCH-Operator-Token"),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    expected = configured_operator_token()
    if not expected:
        append_event(component="backend", event_type="auth", message="Xác thực thất bại: operator token chưa được cấu hình.", severity="error", error_code="AUTH_NOT_CONFIGURED")
        raise ApiError(
            status_code=503,
            error_code="AUTH_NOT_CONFIGURED",
            message_vi=f"Chua cau hinh {TOKEN_ENV} cho dashboard operator.",
        )

    provided = (x_cch_operator_token or "").strip()
    if not provided and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            provided = value.strip()

    if not provided:
        append_event(component="backend", event_type="auth", message="Xác thực thất bại: thiếu operator token.", severity="warning", error_code="AUTH_REQUIRED")
        raise ApiError(
            status_code=401,
            error_code="AUTH_REQUIRED",
            message_vi="Can IT operator token de thuc hien thao tac nay.",
        )

    if not secrets.compare_digest(provided, expected):
        append_event(component="backend", event_type="auth", message="Xác thực thất bại: operator token không hợp lệ.", severity="warning", error_code="AUTH_INVALID")
        raise ApiError(
            status_code=403,
            error_code="AUTH_INVALID",
            message_vi="IT operator token khong hop le.",
        )
    return {"role": "it_operator"}
