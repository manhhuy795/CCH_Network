from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request, WebSocket, status


COOKIE_NAME = "cch_it_dashboard_token"
DEFAULT_TOKEN = "it-support-demo"


def dashboard_token() -> str:
    return os.getenv("CCH_DASHBOARD_TOKEN", DEFAULT_TOKEN)


def allowed_origins() -> list[str]:
    raw = os.getenv(
        "CCH_DASHBOARD_ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def valid_token(value: str | None) -> bool:
    expected = dashboard_token()
    return bool(value and expected and secrets.compare_digest(value, expected))


def token_from_request(request: Request) -> str | None:
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return request.headers.get("x-dashboard-token") or request.cookies.get(COOKIE_NAME)


def require_it_dashboard(request: Request) -> None:
    if not valid_token(token_from_request(request)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chỉ phòng IT Support được truy cập dashboard.",
        )


def websocket_has_access(websocket: WebSocket) -> bool:
    auth_header = websocket.headers.get("authorization", "")
    token = None
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    token = token or websocket.query_params.get("token") or websocket.cookies.get(COOKIE_NAME)
    return valid_token(token)
