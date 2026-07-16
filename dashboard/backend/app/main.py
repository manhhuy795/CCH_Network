from __future__ import annotations

import asyncio
import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from .api import router
from .errors import ApiError, error_payload
from .live_page import LIVE_DASHBOARD_HTML
from .live_mininet import pair_realtime_metrics
from .metrics import current_metrics
from .runtime_health import websocket_connected, websocket_disconnected
from .security import cors_origin_regex, cors_origins


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Hybrid MPLS + SDN Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_origin_regex=cors_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-CCH-Operator-Token", "Authorization"],
)
app.include_router(router)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "").strip()
    request.state.request_id = supplied[:128] if supplied else uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    logging.warning(
        "api_error request_id=%s code=%s message=%s technical=%r",
        _request_id(request),
        exc.error_code,
        exc.message_vi,
        exc.technical_detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.error_code, exc.message_vi, _request_id(request), exc.technical_detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "VALIDATION_ERROR",
            "Du lieu request khong hop le.",
            _request_id(request),
            exc.errors(),
        ),
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    message = str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload("HTTP_ERROR", message, _request_id(request)),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logging.error(
        "unhandled_api_error request_id=%s path=%s",
        _request_id(request),
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content=error_payload(
            "INTERNAL_ERROR",
            "Backend gap loi noi bo. Hay dung request ID de tra log.",
            _request_id(request),
        ),
    )


@app.get("/")
def root():
    return HTMLResponse(LIVE_DASHBOARD_HTML)


@app.get("/live")
def live_dashboard():
    return HTMLResponse(LIVE_DASHBOARD_HTML)


@app.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    await websocket.accept()
    websocket_connected()
    try:
        source = websocket.query_params.get("source")
        destination = websocket.query_params.get("destination")
        try:
            interval = float(websocket.query_params.get("interval", "2"))
        except ValueError:
            interval = 2.0
        previous_bytes = None
        previous_time = None
        while True:
            if source and destination:
                payload = pair_realtime_metrics(source, destination, previous_bytes, previous_time)
                previous_bytes = int(payload.get("flow_bytes") or 0)
                previous_time = time.time()
                await websocket.send_json(payload)
            else:
                await websocket.send_json(current_metrics())
            await asyncio.sleep(max(2, min(interval, 10)))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        request_id = uuid.uuid4().hex
        logging.error(
            "unhandled_websocket_error request_id=%s",
            request_id,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        await websocket.close(code=1011, reason=f"request_id={request_id}")
    finally:
        websocket_disconnected()
