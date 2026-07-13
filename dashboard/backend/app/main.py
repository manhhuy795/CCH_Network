from __future__ import annotations

import asyncio
import logging
import time

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .api import router
from .live_page import LIVE_DASHBOARD_HTML
from .live_mininet import pair_realtime_metrics
from .metrics import current_metrics


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Hybrid MPLS + SDN Dashboard API", version="0.1.0")
app.state.failed_links = set()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root():
    return HTMLResponse(LIVE_DASHBOARD_HTML)


@app.get("/live")
def live_dashboard():
    return HTMLResponse(LIVE_DASHBOARD_HTML)


@app.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    await websocket.accept()
    source = websocket.query_params.get("source")
    destination = websocket.query_params.get("destination")
    interval = float(websocket.query_params.get("interval", "2"))
    previous_bytes = None
    previous_time = None
    while True:
        if source and destination:
            payload = pair_realtime_metrics(source, destination, previous_bytes, previous_time)
            previous_bytes = int(payload.get("byte_count") or 0)
            previous_time = time.time()
            await websocket.send_json(payload)
        else:
            await websocket.send_json(current_metrics())
        await asyncio.sleep(max(2, min(interval, 10)))
