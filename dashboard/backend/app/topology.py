from __future__ import annotations

from . import mininet_control
from .live_mininet import topology_payload


def get_topology() -> dict:
    payload = topology_payload()
    status = mininet_control.get_link_status()
    live_link_control = bool(status.get("ok"))
    runtime_links = status.get("links", {}) if live_link_control else {}
    for link in payload.get("links", []):
        link["status"] = runtime_links.get(link["id"], "up")
    payload.setdefault("summary", {})["live_link_control"] = live_link_control
    payload["summary"]["link_control_message"] = status.get("message", "Mininet control agent ready.")
    return payload
