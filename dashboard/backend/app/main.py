from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .live_page import LIVE_DASHBOARD_HTML
from .metrics import current_metrics


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Hybrid MPLS + SDN Dashboard API", version="0.1.0")
app.state.failed_links = set()
ASSET_DIR = Path(__file__).resolve().parents[3] / "docs" / "assets"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")


@app.get("/")
def root():
    return HTMLResponse(LIVE_DASHBOARD_HTML)


@app.get("/live")
def live_dashboard():
    return HTMLResponse(LIVE_DASHBOARD_HTML)


@app.websocket("/ws/metrics")
async def ws_metrics(websocket: WebSocket):
    await websocket.accept()
    while True:
        await websocket.send_json(current_metrics())
        await asyncio.sleep(2)
