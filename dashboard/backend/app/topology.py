from __future__ import annotations

from . import mininet_control
from .live_mininet import topology_payload


def get_topology() -> dict:
    payload = topology_payload()
    status = mininet_control.get_link_status()
    runtime = mininet_control.live_status()
    live_link_control = bool(status.get("ok"))
    runtime_links = status.get("links", {}) if live_link_control else {}
    for link in payload.get("links", []):
        link["status"] = runtime_links.get(link["id"], "up")
    bridges = runtime.get("bridges", {}) if isinstance(runtime.get("bridges"), dict) else {}
    for device in payload.get("devices", []):
        if not device.get("controller_managed"):
            continue
        if runtime.get("ok"):
            device["status"] = "online" if bridges.get(device["logical_name"]) else "offline"
        else:
            device["status"] = "unknown"
        device["runtime_status_source"] = "mininet_control_agent"
    for node in payload.get("nodes", []):
        matching = next((item for item in payload.get("devices", []) if item["logical_name"] == node.get("id")), None)
        if matching:
            node["status"] = matching["status"]
            node["runtime_bridge"] = matching.get("runtime_bridge")
    payload.setdefault("summary", {})["live_link_control"] = live_link_control
    payload["summary"]["link_control_message"] = status.get("message", "Mininet control agent ready.")
    return payload
