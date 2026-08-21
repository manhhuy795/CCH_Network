from __future__ import annotations

from . import mininet_control
from .live_mininet import topology_payload


def _normalize_topology_contract(payload: dict) -> None:
    """Keep design-only objects out of live status mutation and runtime links."""
    contract = payload.setdefault("topology_contract", {})
    contract.setdefault("design_only_is_runtime", False)
    for item in payload.get("design_nodes", []):
        item["representation"] = "design_only"
        item["controller_managed"] = False
        item["status"] = "design_only"
        item["status_source"] = "source_of_truth"
        item["runtime_bridge"] = None


def get_topology() -> dict:
    payload = topology_payload()
    _normalize_topology_contract(payload)
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
    payload["summary"]["design_only_node_count"] = len(payload.get("design_nodes", []))
    payload["summary"]["runtime_node_count"] = len(payload.get("devices", []))
    return payload
