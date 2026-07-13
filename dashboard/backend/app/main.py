from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel
from fastapi import FastAPI, Response, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .api import router
from .live_page import LIVE_DASHBOARD_HTML, LIVE_LOGIN_HTML
from .metrics import current_metrics
from .security import COOKIE_NAME, allowed_origins, valid_token, token_from_request, websocket_has_access


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Hybrid MPLS + SDN Dashboard API", version="0.1.0")
app.state.failed_links = set()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


class LoginPayload(BaseModel):
    token: str


@app.post("/auth/login")
def login(payload: LoginPayload, response: Response):
    if not valid_token(payload.token):
        response.status_code = 401
        return {"ok": False, "message": "Sai token IT Support."}
    response.set_cookie(
        COOKIE_NAME,
        payload.token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 8,
    )
    return {"ok": True, "message": "Đăng nhập IT Support thành công."}


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True, "message": "Đã đăng xuất dashboard IT."}


@app.get("/auth/status")
def auth_status(request: Request):
    ok = valid_token(token_from_request(request))
    return {"ok": ok, "role": "IT Support" if ok else None}


@app.get("/")
def root(request: Request):
    return HTMLResponse(LIVE_DASHBOARD_HTML if valid_token(token_from_request(request)) else LIVE_LOGIN_HTML)


@app.get("/live")
def live_dashboard(request: Request):
    return HTMLResponse(LIVE_DASHBOARD_HTML if valid_token(token_from_request(request)) else LIVE_LOGIN_HTML)


@app.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    if not websocket_has_access(websocket):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    while True:
        await websocket.send_json(current_metrics())
        await asyncio.sleep(2)
