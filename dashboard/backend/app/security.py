from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException, status


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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Chua cau hinh {TOKEN_ENV} cho dashboard operator.",
        )

    provided = (x_cch_operator_token or "").strip()
    if not provided and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            provided = value.strip()

    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chi IT operator co token hop le moi duoc thuc hien thao tac nay.",
        )
    return {"role": "it_operator"}
