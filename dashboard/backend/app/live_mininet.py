from __future__ import annotations

import json
import ipaddress
import math
import re
import shutil
import threading
import time
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import repo  # Đảm bảo repository root có trong sys.path.
from . import mininet_control
from scripts.network_model import architecture_links, controlled_switches, load_network_model, runtime_switch_map, runtime_switch_name
from sdn_mpls_demo.firewall_nftables import FIREWALL_NAMES, build_firewall_plans
from sdn_mpls_demo.policy_engine import GROUP_PATHS, POLICY_FLOW_PROFILES, PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_FILE = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
RUNTIME_FLOWS_FILE = REPO_ROOT / "sdn_mpls_demo" / "runtime" / "installed_flows.json"
NETWORK_MODEL = load_network_model()
ENGINE = PolicyEngine(POLICY_FILE)
CONTROLLED_SWITCHES = controlled_switches(NETWORK_MODEL)
MANUAL_BLOCK_COOKIE_BASE = 0x9000
COOKIE_MASK = "0xffffffffffffffff"
IPERF_SESSION_DIR = "/tmp/cch_iperf"
IPERF_BASE_PORT = 5201
IPERF_PORT_SPAN = 200
IPERF_MAX_CONCURRENT = 4
IPERF_SESSION_TTL_SECONDS = 120

_IPERF_GLOBAL_LOCK = threading.Lock()
_IPERF_DESTINATION_LOCKS: dict[str, threading.Lock] = {}
_IPERF_ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}
_IPERF_PORT_CURSOR = 0

POLICY_COOKIE_HINTS = {
    policy_id: f"0x{int(profile['cookie']):x}"
    for policy_id, profile in POLICY_FLOW_PROFILES.items()
} | {
    "policy_engine_default": None,
    "link_down": None,
}

POLICY_PRIORITY_HINTS = {
    policy_id: int(profile["priority"])
    for policy_id, profile in POLICY_FLOW_PROFILES.items()
} | {
    "policy_engine_default": None,
    "link_down": None,
}

CLUSTER_SOURCES = {
    "project_a": ("h20_01", "Dự án A / VLAN 20"),
    "project_b": ("h30_01", "Dự án B / VLAN 30"),
    "project_c": ("h40_01", "Dự án C / VLAN 40"),
    "telesale": ("h50_01", "Telesale / VLAN 50"),
    "backoffice": ("h60_01", "BackOffice / VLAN 60"),
    "it_support": ("h70_01", "IT Support / VLAN 70"),
}

CLUSTER_ALLOW_TARGETS = {
    "project_a": ("h90", "hzalo", "hcall", "hinternet"),
    "project_b": ("h90", "hzalo", "hcall", "hinternet"),
    "project_c": ("h90", "hzalo", "hcall", "hinternet"),
    "telesale": ("h90", "hzalo", "hcall", "hinternet"),
    "backoffice": ("h90", "hzalo", "hcall", "hinternet"),
    "it_support": ("h20_01", "h30_01", "h40_01", "h50_01", "h60_01", "h90", "hzalo", "hcall", "hinternet"),
}

CLUSTER_DENY_TARGETS = {
    "project_a": ("h30_01", "h40_01", "h50_01", "h60_01", "hsocial"),
    "project_b": ("h20_01", "h40_01", "h50_01", "h60_01", "hsocial"),
    "project_c": ("h20_01", "h30_01", "h50_01", "h60_01", "hsocial"),
    "telesale": ("h20_01", "h30_01", "h40_01", "h60_01", "hsocial"),
    "backoffice": ("h50_01", "h20_01", "h30_01", "h40_01", "hsocial"),
    "it_support": ("hsocial",),
}


def reload_policy_engine() -> None:
    global ENGINE
    ENGINE = PolicyEngine(POLICY_FILE)

INFRA_NODES = [
    ("c0", NETWORK_MODEL["infrastructure"]["c0"]["label"], "controller", NETWORK_MODEL["infrastructure"]["c0"].get("subtitle", "")),
    *(
        (name, switch["label"], "switch", switch.get("subtitle", ""))
        for name, switch in NETWORK_MODEL["switches"].items()
    ),
    *(
        (name, node["label"], node["type"], node.get("subtitle", ""))
        for name, node in NETWORK_MODEL["infrastructure"].items()
        if name != "c0"
    ),
]

ARCHITECTURE_LINKS = architecture_links(NETWORK_MODEL)
RUNTIME_BRIDGE_MAP = runtime_switch_map(NETWORK_MODEL)
COMBINED_ACCEPTANCE_FILE = REPO_ROOT / "runtime_reports" / "phase44_45_combined_summary.json"
DASHBOARD_SITE_LABELS = {
    "hq": "Trụ sở chính HQ",
    "telesale": "Telesale",
}


def dashboard_site_id(source_site: str | None) -> str:
    """Map source-of-truth site IDs to the two public physical site IDs."""
    return "telesale" if source_site == "branch_telesale" else str(source_site or "unknown")


def phase44_runtime_status() -> dict[str, Any]:
    """Expose evidence state without treating static config or stale files as live proof."""
    pending = {
        "status": "pending",
        "message_vi": "Chưa chạy Combined Acceptance trên Ubuntu; firewall/NAT runtime chưa được xác minh.",
        "evidence_available": False,
        "nat_conclusion": "NAT REQUIREMENT NOT YET CONCLUDED",
    }
    live = mininet_control.live_status()
    if not isinstance(live, dict) or live.get("ok") is not True or live.get("available") is False:
        return pending
    try:
        payload = json.loads(COMBINED_ACCEPTANCE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return pending
    if payload.get("overall_status") != "PASS" or payload.get("phase44_runtime_verified") is not True:
        return {**pending, "evidence_available": True, "message_vi": "Có evidence nhưng chưa đủ điều kiện xác nhận runtime."}
    return {
        "status": "verified",
        "message_vi": "Combined Acceptance đã xác nhận runtime Phase 44 trên Ubuntu.",
        "evidence_available": True,
        "nat_conclusion": str(payload.get("nat_conclusion") or "NAT REQUIREMENT NOT YET CONCLUDED"),
        "checked_at": payload.get("checked_at"),
    }


def firewall_inventory() -> list[dict[str, Any]]:
    """Return two-site firewall contract; counters are null until read from live nftables."""
    acceptance = phase44_runtime_status()
    try:
        plans = build_firewall_plans()
    except (KeyError, OSError, ValueError) as exc:
        plans = {}
        plan_error = str(exc)
    else:
        plan_error = None
    runtime_response = mininet_control.firewall_status()
    runtime_firewalls = runtime_response.get("firewalls", {}) if isinstance(runtime_response, dict) else {}
    inventory: list[dict[str, Any]] = []
    for firewall_name in FIREWALL_NAMES:
        plan = plans.get(firewall_name, {})
        runtime = runtime_firewalls.get(firewall_name, {}) if isinstance(runtime_firewalls, dict) else {}
        runtime_ok = bool(runtime.get("ok"))
        inventory.append({
            "name": firewall_name,
            "logical_name": firewall_name,
            "site": dashboard_site_id(plan.get("site")),
            "inside_interface": plan.get("inside_interface"),
            "outside_interface": plan.get("outside_interface"),
            "inside_logical_interface": plan.get("inside_logical_interface"),
            "outside_logical_interface": plan.get("outside_logical_interface"),
            "ipv4_forwarding": runtime.get("ipv4_forwarding") if runtime_ok else None,
            "nftables_table": plan.get("family", "inet") + " " + plan.get("table_name", "cch_filter"),
            "chain": "forward",
            "rule_count": runtime.get("rule_count") if runtime_ok else None,
            "expected_rule_count": len(plan.get("rules", ())) + 8 if plan else None,
            "counters": runtime.get("counters") if runtime_ok else None,
            "nftables_status": "available" if runtime_ok else "unavailable",
            "runtime_status": acceptance["status"] if acceptance["status"] == "verified" else ("pending" if runtime_ok else "unavailable"),
            "nat": {
                "configured": bool(plan.get("nat", {}).get("enabled")) if plan else False,
                "status": acceptance["status"] if acceptance["status"] == "verified" else "pending",
                "conclusion": acceptance["nat_conclusion"],
            },
            "error_code": None if runtime_ok else str(runtime.get("error_code") or ("FIREWALL_PLAN_INVALID" if plan_error else "FIREWALL_UNAVAILABLE")),
            "technical_detail": runtime if runtime else {"plan_error": plan_error},
        })
    return inventory


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None



def topology_payload() -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    hosts = sorted(
        [{**host, "site": dashboard_site_id(host.get("site"))} for host in ENGINE.hosts.values()],
        key=lambda item: (item["kind"] != "user", item["name"]),
    )
    for name, group in ENGINE.groups.items():
        group_hosts = [host for host in hosts if host.get("group") == name and host.get("kind") == "user"]
        item = {
            "id": name,
            "label": group["label"],
            "type": "user_group",
            "site": dashboard_site_id(group.get("site")),
            "vlan": int(group["vlan"]),
            "count": int(group["count"]),
            "subnet": group["subnet"],
            "switch": group["switch"],
            "hosts": group_hosts,
        }
        nodes.append(item)
        groups.append(item)

    devices: list[dict[str, Any]] = []
    for node_id, label, node_type, subtitle in INFRA_NODES:
        switch = NETWORK_MODEL.get("switches", {}).get(node_id)
        infrastructure = NETWORK_MODEL.get("infrastructure", {}).get(node_id, {})
        source = switch or infrastructure
        is_controlled = bool(switch and switch.get("controlled"))
        device = {
            "id": node_id,
            "logical_name": node_id,
            "label": label,
            "type": node_type,
            "role": source.get("role", node_type),
            "subtitle": subtitle,
            "site": dashboard_site_id(source.get("site")),
            "dpid": source.get("dpid"),
            "runtime_bridge": runtime_switch_name(NETWORK_MODEL, node_id) if switch else None,
            "controller_managed": is_controlled,
            "status": "unknown",
            "status_source": "live_mininet",
        }
        nodes.append(device)
        devices.append(device)

    for service_name, service in ENGINE.services.items():
        nodes.append({
            "id": service_name,
            "logical_name": service_name,
            "label": service["label"],
            "type": "blocked_service" if service_name == "hsocial" else "service",
            "site": "internet",
            "ip": service["ip"],
            "controller_managed": False,
            "status": "unknown",
            "status_source": "live_mininet",
        })

    links = [
        {
            "id": f"{source}-{target}",
            "source": source,
            "target": target,
            "type": link_type,
            "status": "up",
        }
        for source, target, link_type in ARCHITECTURE_LINKS
    ]
    site_groups = {
        site_id: [group["id"] for group in groups if group["site"] == site_id]
        for site_id in ("hq", "telesale")
    }
    site_devices = {
        site_id: [device["logical_name"] for device in devices if device["site"] == site_id]
        for site_id in ("hq", "telesale")
    }
    sites = [
        {
            "id": site_id,
            "label": DASHBOARD_SITE_LABELS[site_id],
            "kind": "physical",
            "source_id": "branch_telesale" if site_id == "telesale" else site_id,
            "groups": site_groups[site_id],
            "devices": site_devices[site_id],
        }
        for site_id in ("hq", "telesale")
    ]
    firewalls = firewall_inventory()
    return {
        "nodes": nodes,
        "groups": groups,
        "hosts": hosts,
        "links": links,
        "metadata": ENGINE.data["metadata"],
        "sites": sites,
        "site_ids": ["hq", "telesale"],
        "devices": devices,
        "logical_switches": [device for device in devices if device["controller_managed"]],
        "runtime_bridge_map": dict(RUNTIME_BRIDGE_MAP),
        "ce_nodes": [device for device in devices if device["type"] == "router"],
        "firewalls": firewalls,
        "mpls": {
            "id": "mpls_cloud",
            "status": "logical_only",
            "controller_managed": False,
            "path_between": ["ce_hq", "mpls_cloud", "ce_telesale"],
        },
        "internet_zone": {"id": "internet_zone", "status": "logical_only", "controller_managed": False},
        "phase44_runtime": phase44_runtime_status(),
        "policy_map": policy_map_payload(),
        "summary": {
            "user_count": sum(int(group["count"]) for group in ENGINE.groups.values()),
            "service_count": len(ENGINE.services),
            "controlled_ovs_count": len(CONTROLLED_SWITCHES),
            "site_count": 2,
            "ce_count": 2,
            "firewall_count": 2,
        },
    }


def representative_endpoint(node_id: str) -> str:
    if node_id in ENGINE.groups:
        group = ENGINE.groups[node_id]
        return f"{group['prefix']}_01"
    return node_id


def policy_map_payload() -> dict[str, Any]:
    selectable = [*ENGINE.groups.keys(), *ENGINE.services.keys()]
    names = {
        **{name: group["label"] for name, group in ENGINE.groups.items()},
        **{name: service["label"] for name, service in ENGINE.services.items()},
    }
    payload: dict[str, Any] = {}
    for source_id in selectable:
        source_endpoint = representative_endpoint(source_id)
        allow: list[str] = []
        deny: list[str] = []
        notes: dict[str, str] = {}
        for destination_id in selectable:
            if destination_id == source_id:
                continue
            destination_endpoint = representative_endpoint(destination_id)
            decision = policy_decision(source_endpoint, destination_endpoint)
            target_list = allow if decision["action"] == "allow" else deny
            target_list.append(destination_id)
            notes[destination_id] = decision["reason"]
        payload[source_id] = {
            "title": names.get(source_id, source_id),
            "allow": allow,
            "deny": deny,
            "notes": notes,
        }
    return payload


def policy_payload() -> dict[str, Any]:
    return {
        "metadata": ENGINE.data["metadata"],
        "host_groups": ENGINE.groups,
        "services": ENGINE.services,
        "policies": ENGINE.policies,
    }


def policy_decision(source: str, destination: str) -> dict[str, Any]:
    return ENGINE.decide(source, destination)


def _endpoint_labels(name: str) -> set[str]:
    endpoint = ENGINE.endpoint(name)
    labels = {name}
    if not endpoint:
        return labels
    labels.add(endpoint["ip"])
    if endpoint.get("kind") == "user":
        group_name = endpoint.get("group")
        labels.add(group_name)
        labels.add(ENGINE.groups[group_name]["subnet"])
    elif endpoint.get("kind") == "service":
        labels.add(f"{endpoint['ip']}/32")
    return {str(item) for item in labels if item is not None}


def _load_installed_flow_records() -> list[dict[str, Any]]:
    """Load controller history for the OpenFlow inventory view only.

    This file is intentionally not used as proof that a flow is live.  The
    controller can restart, an OVS bridge can be recreated, or the file can
    outlive the topology that created it.
    """
    try:
        payload = json.loads(RUNTIME_FLOWS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return payload if isinstance(payload, list) else []


def _flow_matches_endpoint(flow: dict[str, Any], source: str, destination: str, action: str) -> bool:
    source_labels = _endpoint_labels(source)
    destination_labels = _endpoint_labels(destination)
    flow_source = str(flow.get("source", ""))
    flow_destination = str(flow.get("destination", ""))
    flow_action = str(flow.get("action", "")).upper()
    return (
        flow_source in source_labels
        and flow_destination in destination_labels
        and (not action or flow_action == action.upper())
    )


def _normalize_cookie(value: Any) -> int | None:
    try:
        if isinstance(value, str):
            return int(value, 0)
        return int(value)
    except (TypeError, ValueError):
        return None


def _flow_match_label(value: str | None) -> str:
    """Map an OVS network match to its policy group/service label."""
    if not value:
        return "*"
    candidate = str(value).strip()
    try:
        network = ipaddress.ip_network(candidate, strict=False)
    except ValueError:
        return "*"

    for group_name, group in ENGINE.groups.items():
        if network == ipaddress.ip_network(str(group["subnet"]), strict=False):
            return str(group_name)
    for service_name, service in ENGINE.services.items():
        service_network = ipaddress.ip_network(f"{service['ip']}/32", strict=False)
        if network == service_network:
            return str(service_name)
    return "*"


def _runtime_flow_matches_contract(
    source: str,
    destination: str,
    decision: dict[str, Any],
    flow: dict[str, Any],
) -> bool:
    """Validate a flow returned by a live OVS lookup against static intent."""
    policy = _policy_hint(source, destination, decision)
    expected_cookie = POLICY_COOKIE_HINTS.get(policy)
    expected_priority = POLICY_PRIORITY_HINTS.get(policy)
    expected_action = "DROP" if decision.get("action") == "deny" else "ALLOW"

    if expected_cookie is None or expected_priority is None:
        return False
    if str(flow.get("switch", "")) not in _runtime_switch_candidates(decision):
        return False
    if _normalize_cookie(flow.get("cookie")) != _normalize_cookie(expected_cookie):
        return False
    try:
        if int(flow.get("priority")) != int(expected_priority):
            return False
    except (TypeError, ValueError):
        return False
    if str(flow.get("action", "")).upper() != expected_action:
        return False
    if not _flow_matches_endpoint(flow, source, destination, expected_action):
        return False

    # Parsed live records must retain the actual match/action text.  This
    # prevents a hand-built metadata record from being treated as OVS proof.
    raw_match = str(flow.get("raw_match", ""))
    raw_action = str(flow.get("raw_action", ""))
    if not raw_match or not raw_action:
        return False
    source_network = ENGINE.endpoint(source)
    destination_network = ENGINE.endpoint(destination)
    if not source_network or not destination_network:
        return False
    source_subnet = str(ENGINE.groups[source_network["group"]]["subnet"]) if source_network.get("kind") == "user" else f"{source_network['ip']}/32"
    destination_subnet = str(ENGINE.groups[destination_network["group"]]["subnet"]) if destination_network.get("kind") == "user" else f"{destination_network['ip']}/32"
    if source_subnet.split("/")[0] not in raw_match or destination_subnet.split("/")[0] not in raw_match:
        return False
    if expected_action == "DROP" and "drop" not in raw_action.lower():
        return False
    if expected_action == "ALLOW" and not any(token in raw_action.lower() for token in ("normal", "output", "set_field")):
        return False
    return True


def _matching_runtime_flow(
    source: str,
    destination: str,
    decision: dict[str, Any],
    runtime_flows: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return a validated flow from an explicit live lookup result only.

    The optional argument is deliberate: omitting it means no runtime
    evidence.  In particular, this function never falls back to the stale
    controller inventory file or process-global runtime state.
    """
    flows = runtime_flows or []
    if not flows:
        return None
    candidates = [
        flow for flow in flows
        if _runtime_flow_matches_contract(source, destination, decision, flow)
    ]
    blocked_at = decision.get("blocked_at")
    if blocked_at:
        preferred = [flow for flow in candidates if flow.get("enforcement_switch") == blocked_at or flow.get("switch") == blocked_at]
        if preferred:
            candidates = preferred
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: int(item.get("priority") or 0), reverse=True)[0]


def _runtime_switch_candidates(decision: dict[str, Any]) -> list[str]:
    blocked_at = str(decision.get("blocked_at") or "")
    if blocked_at in CONTROLLED_SWITCHES:
        return [blocked_at]
    return [
        str(node)
        for node in decision.get("path", [])
        if str(node) in CONTROLLED_SWITCHES
    ]


def _lookup_live_runtime_flow(source: str, destination: str, decision: dict[str, Any]) -> dict[str, Any] | None:
    """Query OVS through the control agent and validate one live policy flow."""
    for switch in _runtime_switch_candidates(decision):
        ok, output = mininet_control.dump_flows(switch)
        if not ok:
            continue
        parsed = [
            flow
            for line in output.splitlines()
            if (flow := parse_flow_line(line, switch)) is not None
        ]
        if (match := _matching_runtime_flow(source, destination, decision, parsed)) is not None:
            return match
    return None


def _policy_hint(source: str, destination: str, decision: dict[str, Any]) -> str:
    source_data = ENGINE.endpoint(source)
    destination_data = ENGINE.endpoint(destination)
    reason = str(decision.get("reason", "")).lower()
    if decision.get("failed_link"):
        return "link_down"
    if (source == "h70_01" or destination == "h70_01") and (source == "hsocial" or destination == "hsocial"):
        return "it_social_block"
    if destination == "h70_01" and decision.get("action") == "deny":
        return "it_inbound_block"
    if "least privilege" in reason and decision.get("action") == "deny":
        return "reactive_policy_drop"
    if "it support" in reason:
        return "it_support"
    if destination == "h90" or source == "h90":
        return "voice"
    if destination in {"hzalo", "hcall", "hinternet"}:
        return "firewall_allowed_service"
    if source_data and source_data.get("kind") == "service" and destination_data and destination_data.get("kind") == "user":
        return "firewall_inbound_block"
    if destination == "hsocial" or source == "hsocial":
        return "firewall_social_block"
    if "vlan 50" in reason or "vlan 60" in reason:
        return "telesale_backoffice_isolation"
    if "vlan" in reason or "cach ly" in reason:
        return "hq_project_isolation"
    if decision.get("action") == "deny":
        return "reactive_policy_drop"
    return "policy_engine_default"


def _fallback_enforcement_switch(decision: dict[str, Any]) -> str | None:
    blocked_at = decision.get("blocked_at")
    if blocked_at in {"fw_hq", "fw_telesale"}:
        return str(blocked_at)
    if blocked_at in CONTROLLED_SWITCHES:
        return str(blocked_at)
    for node in reversed(decision.get("path", [])):
        switch = ENGINE.switches.get(str(node), {})
        if node in CONTROLLED_SWITCHES and switch.get("role") in {"hq_core", "branch_distribution"}:
            return str(node)
    return next((node for node in decision.get("path", []) if node in CONTROLLED_SWITCHES), None)


def enrich_decision(
    source: str,
    destination: str,
    decision: dict[str, Any],
    runtime_flow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enriched = dict(decision)
    flow = _matching_runtime_flow(source, destination, enriched, [runtime_flow] if runtime_flow else None)
    live_flow_verified = flow is not None
    policy = flow.get("policy") if flow else _policy_hint(source, destination, enriched)
    enriched.update(
        {
            "src": source,
            "dst": destination,
            "failed_link": enriched.get("failed_link"),
            "enforcement_switch": (
                (flow.get("enforcement_switch") or flow.get("switch"))
                if flow
                else _fallback_enforcement_switch(enriched)
            ),
            "policy": policy,
            "cookie": flow.get("cookie") if flow else POLICY_COOKIE_HINTS.get(str(policy)),
            "priority": flow.get("priority") if flow else POLICY_PRIORITY_HINTS.get(str(policy)),
            "flow_runtime_available": live_flow_verified,
            "metadata_source": "controller_runtime" if live_flow_verified else "policy_engine",
            "runtime_flow": flow,
        }
    )
    return enriched



def parse_ping(output: str) -> dict[str, Any]:
    result: dict[str, Any] = {"raw": output}
    summary = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received, ([0-9.]+)% packet loss", output)
    if summary:
        result.update(
            transmitted=int(summary.group(1)),
            received=int(summary.group(2)),
            packet_loss_percent=float(summary.group(3)),
        )
    rtt = re.search(r"= ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+) ms", output)
    if rtt:
        result.update(
            rtt_min_ms=float(rtt.group(1)),
            rtt_avg_ms=float(rtt.group(2)),
            rtt_max_ms=float(rtt.group(3)),
            jitter_ms=float(rtt.group(4)),
        )
    result["reachable"] = result.get("received", 0) > 0
    return result


def ping(source: str, destination: str, count: int = 3) -> dict[str, Any]:
    source_data = ENGINE.endpoint(source)
    destination_data = ENGINE.endpoint(destination)
    if not source_data or not destination_data:
        return {"ok": False, "message": "Nguồn hoặc đích không hợp lệ.", "raw": ""}
    decision = policy_decision(source, destination)
    policy_action = decision.get("action")
    down_link = mininet_control.first_down_link(decision.get("path", []))
    agent_response = mininet_control.ping_detailed(source, destination_data["ip"], count)
    output = str(agent_response.get("raw") or agent_response.get("message") or "")
    ok = bool(agent_response.get("ok"))
    agent_error = agent_response.get("error_code")
    if agent_error in {"MININET_NOT_RUNNING", "AGENT_NOT_READY", "AGENT_TIMEOUT", "AGENT_DISCONNECTED"}:
        return {
            "ok": False,
            "error_code": agent_error,
            "message": str(agent_response.get("message") or "Khong the gui ping qua Mininet Control Agent."),
            "decision": enrich_decision(source, destination, decision),
            "result": {"reachable": False, "raw": output},
            "raw": output,
        }
    result = parse_ping(output)
    reachable = bool(result["reachable"])
    if down_link and not reachable:
        blocked_at = down_link["blocked_at"]
        path = decision.get("path", [])
        stop_index = path.index(blocked_at) if blocked_at in path else 0
        decision = {
            **decision,
            "action": "deny",
            "path": path[: stop_index + 1],
            "blocked_at": blocked_at,
            "failed_link": down_link["link_id"],
            "reason": "Lien ket that trong Mininet dang DOWN nen packet dung tai node truoc link loi.",
        }
    elif not reachable and decision["action"] == "allow":
        decision = {
            **decision,
            "action": "deny",
            "blocked_at": decision["path"][-1] if decision["path"] else None,
            "reason": "Policy cho phép nhưng lab không nhận phản hồi. Hãy kiểm tra controller, flow và link Mininet.",
        }
    decision = enrich_decision(source, destination, decision)
    if ok:
        runtime_flow = _lookup_live_runtime_flow(source, destination, decision)
        if runtime_flow:
            decision = enrich_decision(source, destination, decision, runtime_flow=runtime_flow)
    error_code = None
    if not reachable and policy_action == "deny":
        error_code = "POLICY_DENIED"
    elif not reachable:
        error_code = "PING_FAILED"
    return {
        "ok": ok and reachable,
        "error_code": error_code,
        "message": f"{source} → {destination}: {'PING THÀNH CÔNG' if reachable else 'PING THẤT BẠI'}",
        "decision": decision,
        "result": result,
        "raw": output,
    }


def parse_iperf3(output: str) -> dict[str, Any]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        return {"parse_warning": str(exc), "raw": output}
    if not isinstance(payload, dict):
        return {
            "parse_warning": f"iperf3 JSON phai la object, nhan duoc {type(payload).__name__}.",
            "raw": output,
        }
    end = payload.get("end", {})
    if not isinstance(end, dict):
        return {"parse_warning": "Field end cua iperf3 khong phai object.", "raw": output}
    summary = end.get("sum_received") or end.get("sum") or {}
    if not isinstance(summary, dict):
        return {"parse_warning": "Field summary cua iperf3 khong phai object.", "raw": output}
    throughput = None
    parse_warnings = []
    if summary.get("bits_per_second") is not None:
        try:
            throughput = round(float(summary["bits_per_second"]) / 1_000_000, 3)
        except (TypeError, ValueError):
            parse_warnings.append("bits_per_second khong phai so")
    result = {
        "throughput_mbps": throughput,
        "jitter_ms": summary.get("jitter_ms"),
        "packet_loss_percent": summary.get("lost_percent"),
        "lost_packets": summary.get("lost_packets"),
        "total_datagrams": summary.get("packets"),
        "transferred_bytes": summary.get("bytes"),
        "raw": output,
    }
    missing = [field for field in ("bits_per_second", "bytes") if field not in summary]
    if missing:
        parse_warnings.append(f"Thieu field iperf3: {', '.join(missing)}")
    if parse_warnings:
        result["parse_warning"] = "; ".join(parse_warnings)
    return result


def _cleanup_stale_iperf_sessions(now: float | None = None) -> None:
    reference = now if now is not None else time.time()
    stale = [
        session_id
        for session_id, session in _IPERF_ACTIVE_SESSIONS.items()
        if reference - float(session.get("started_at", reference)) > IPERF_SESSION_TTL_SECONDS
    ]
    for session_id in stale:
        _IPERF_ACTIVE_SESSIONS.pop(session_id, None)


def _destination_lock(destination: str) -> threading.Lock:
    with _IPERF_GLOBAL_LOCK:
        lock = _IPERF_DESTINATION_LOCKS.get(destination)
        if lock is None:
            lock = threading.Lock()
            _IPERF_DESTINATION_LOCKS[destination] = lock
        return lock


def _register_iperf_session(source: str, destination: str, protocol: str, seconds: int) -> tuple[bool, dict[str, Any]]:
    global _IPERF_PORT_CURSOR
    with _IPERF_GLOBAL_LOCK:
        _cleanup_stale_iperf_sessions()
        if len(_IPERF_ACTIVE_SESSIONS) >= IPERF_MAX_CONCURRENT:
            return False, {
                "ok": False,
                "error_code": "IPERF_CONCURRENCY_LIMIT",
                "message": f"He thong dang co {IPERF_MAX_CONCURRENT} phien iperf. Hay cho phien dang chay ket thuc.",
            }

        used_ports = {int(session["port"]) for session in _IPERF_ACTIVE_SESSIONS.values()}
        port = None
        for _ in range(IPERF_PORT_SPAN):
            candidate = IPERF_BASE_PORT + _IPERF_PORT_CURSOR
            _IPERF_PORT_CURSOR = (_IPERF_PORT_CURSOR + 1) % IPERF_PORT_SPAN
            if candidate not in used_ports:
                port = candidate
                break
        if port is None:
            return False, {
                "ok": False,
                "error_code": "IPERF_PORT_POOL_EXHAUSTED",
                "message": "Khong con port iperf trong pool demo.",
            }

        session_id = uuid.uuid4().hex[:12]
        session = {
            "session_id": session_id,
            "source": source,
            "destination": destination,
            "protocol": protocol,
            "port": port,
            "duration": seconds,
            "started_at": time.time(),
            "log_path": f"{IPERF_SESSION_DIR}/{session_id}.json",
        }
        _IPERF_ACTIVE_SESSIONS[session_id] = session
        return True, session


def _finish_iperf_session(session_id: str) -> None:
    with _IPERF_GLOBAL_LOCK:
        _IPERF_ACTIVE_SESSIONS.pop(session_id, None)


def iperf_runtime_status() -> dict[str, Any]:
    with _IPERF_GLOBAL_LOCK:
        sessions = list(_IPERF_ACTIVE_SESSIONS.values())
    return {
        "active_count": len(sessions),
        "max_concurrent": IPERF_MAX_CONCURRENT,
        "destinations": sorted({str(session.get("destination")) for session in sessions}),
    }


def iperf(source: str, destination: str, protocol: str = "tcp", seconds: int = 5) -> dict[str, Any]:
    protocol = protocol.lower()
    seconds = max(1, min(int(seconds), 30))
    destination_data = ENGINE.endpoint(destination)
    if not ENGINE.endpoint(source) or not destination_data:
        return {"ok": False, "message": "Nguon hoac dich khong hop le.", "raw": ""}
    if protocol not in {"tcp", "udp"}:
        return {"ok": False, "message": "Protocol chi ho tro tcp hoac udp.", "raw": ""}

    decision = policy_decision(source, destination)
    if decision["action"] == "deny":
        return {"ok": False, "message": f"Khong the do bang thong. {decision['reason']}", "decision": decision, "raw": ""}

    destination_lock = _destination_lock(destination)
    if not destination_lock.acquire(blocking=False):
        return {
            "ok": False,
            "error_code": "IPERF_DESTINATION_BUSY",
            "message": f"{destination} dang co phien iperf khac. Hay cho phien do ket thuc roi thu lai.",
            "source": source,
            "destination": destination,
            "protocol": protocol,
            "duration": seconds,
            "decision": decision,
            "raw": "",
        }

    registered, session = _register_iperf_session(source, destination, protocol, seconds)
    if not registered:
        destination_lock.release()
        return {
            **session,
            "source": source,
            "destination": destination,
            "protocol": protocol,
            "duration": seconds,
            "decision": decision,
            "raw": "",
        }

    session_id = str(session["session_id"])
    port = int(session["port"])
    log_path = str(session["log_path"])
    server_pid: str | None = None
    output = ""
    response_payload: dict[str, Any] | None = None
    try:
        server_response = mininet_control.start_iperf_server(destination, port, log_path, session_id)
        server_pid = str(server_response.get("pid") or "") or None
        if not server_response.get("ok") or not server_pid or not server_response.get("listening"):
            response_payload = {
                "ok": False,
                "error_code": server_response.get("error_code") or "IPERF_SERVER_START_FAILED",
                "message": f"Khong khoi dong duoc iperf3 server tren {destination}.",
                "session_id": session_id,
                "source": source,
                "destination": destination,
                "protocol": protocol,
                "port": port,
                "duration": seconds,
                "decision": decision,
                "raw": str(server_response.get("raw") or server_response.get("message") or ""),
            }
            return response_payload

        client_response = mininet_control.run_iperf_client(
            source,
            destination_data["ip"],
            port,
            protocol,
            seconds,
            session_id,
        )
        output = str(client_response.get("raw") or "")
        result = client_response.get("result")
        if not isinstance(result, dict):
            result = parse_iperf3(output)
        parse_warning = client_response.get("parse_warning") or result.get("parse_warning")
        response_payload = {
            "ok": bool(client_response.get("ok")),
            "error_code": client_response.get("error_code"),
            "message": str(
                client_response.get("message")
                or f"{source} -> {destination}: da do bang thong {protocol.upper()} theo session {session_id}"
            ),
            "session_id": session_id,
            "source": source,
            "destination": destination,
            "protocol": protocol,
            "port": port,
            "duration": seconds,
            "decision": decision,
            "result": result,
            "parse_warning": parse_warning,
            "raw": output,
        }
        return response_payload
    finally:
        cleanup_warning = None
        try:
            if server_pid:
                cleanup_response = mininet_control.kill_pid(destination, server_pid, session_id)
                if not cleanup_response.get("ok"):
                    cleanup_warning = str(cleanup_response.get("message") or "Khong cleanup duoc iperf server.")
        except Exception as exc:
            cleanup_warning = f"Cleanup iperf gap loi: {exc}"
        finally:
            _finish_iperf_session(session_id)
            destination_lock.release()
        if cleanup_warning and response_payload is not None:
            response_payload["cleanup_warning"] = cleanup_warning


def estimate_voice_quality(rtt_ms: float, jitter_ms: float, packet_loss_percent: float) -> dict[str, Any]:
    effective_latency = (rtt_ms / 2) + (jitter_ms * 2) + 10
    r_factor = 93.2 - (effective_latency / 40 if effective_latency < 160 else (effective_latency - 120) / 10)
    r_factor = max(0.0, min(100.0, r_factor - packet_loss_percent * 2.5))
    mos = 1 + 0.035 * r_factor + 0.000007 * r_factor * (r_factor - 60) * (100 - r_factor)
    mos = round(max(1.0, min(4.5, mos)), 2)
    checks = {
        "latency": rtt_ms <= 150,
        "jitter": jitter_ms <= 30,
        "packet_loss": packet_loss_percent <= 1,
        "mos": mos >= 4.0,
    }
    passed = all(checks.values())
    return {
        "r_factor": round(r_factor, 1),
        "mos": mos,
        "rating": "Tốt - phù hợp cho cuộc gọi" if passed else "Cần theo dõi chất lượng cuộc gọi",
        "passed": passed,
        "estimation_note": "MOS/R-factor duoc uoc luong tu RTT, packet loss va jitter; khong phai cuoc goi SIP/RTP hoan chinh.",
        "checks": checks,
        "thresholds": {"rtt_ms": 150, "jitter_ms": 30, "packet_loss_percent": 1, "mos": 4.0},
    }


def call_quality(source: str, destination: str, seconds: int = 5) -> dict[str, Any]:
    decision = policy_decision(source, destination)
    if decision["action"] == "deny":
        return {"ok": False, "message": f"Không thể đo chất lượng. {decision['reason']}", "decision": decision, "raw": ""}
    ping_payload = ping(source, destination, count=10)
    if not ping_payload["ok"]:
        return ping_payload
    udp_payload = iperf(source, destination, protocol="udp", seconds=seconds)
    if not udp_payload["ok"]:
        return udp_payload
    ping_result = ping_payload["result"]
    udp_result = udp_payload["result"]
    rtt = float(ping_result.get("rtt_avg_ms") or 0)
    jitter = float(udp_result.get("jitter_ms") or ping_result.get("jitter_ms") or 0)
    loss = max(float(ping_result.get("packet_loss_percent") or 0), float(udp_result.get("packet_loss_percent") or 0))
    quality = estimate_voice_quality(rtt, jitter, loss)
    throughput = float(udp_result.get("throughput_mbps") or 0)
    quality["checks"]["throughput"] = throughput >= 0.1
    quality["passed"] = all(quality["checks"].values())
    result = {
        "rtt_avg_ms": rtt,
        "jitter_ms": jitter,
        "packet_loss_percent": loss,
        "throughput_mbps": throughput,
        **quality,
    }
    return {
        "ok": quality["passed"],
        "measurement_completed": True,
        "message": f"Đã đo chất lượng {source} → {destination}: {quality['rating']}.",
        "decision": decision,
        "result": result,
        "raw": f"=== PING ===\n{ping_payload['raw']}\n\n=== IPERF3 UDP ===\n{udp_payload['raw']}",
    }


def _case_result(name: str, category: str, expected: str, payload: dict[str, Any]) -> dict[str, Any]:
    reachable = bool(payload.get("result", {}).get("reachable", payload.get("ok", False)))
    passed = (expected == "allow" and bool(payload.get("ok"))) or (expected == "deny" and not reachable)
    metric = payload.get("result", {})
    return {
        "name": name,
        "category": category,
        "expected": expected,
        "passed": passed,
        "message": payload.get("message", ""),
        "reason": payload.get("decision", {}).get("reason", ""),
        "rtt_ms": metric.get("rtt_avg_ms"),
        "jitter_ms": metric.get("jitter_ms"),
        "loss_percent": metric.get("packet_loss_percent"),
        "mos": metric.get("mos"),
        "throughput_mbps": metric.get("throughput_mbps"),
        "raw": payload.get("raw", ""),
    }


def cluster_detail_test(cluster: str, seconds: int = 3) -> dict[str, Any]:
    if cluster not in CLUSTER_SOURCES:
        return {"ok": False, "message": f"Không có cụm test: {cluster}", "cases": []}

    source, label = CLUSTER_SOURCES[cluster]
    cases: list[dict[str, Any]] = []

    voice_payload = call_quality(source, "h90", seconds=seconds)
    cases.append(_case_result("Softphone Cfone/Gphone -> PBX/SBC Voice Service", "voice", "allow", voice_payload))

    if "hcall" in CLUSTER_ALLOW_TARGETS[cluster]:
        cases.append(_case_result("Call App/CRM TCP throughput", "application", "allow", iperf(source, "hcall", "tcp", seconds)))
    if "hinternet" in CLUSTER_ALLOW_TARGETS[cluster]:
        cases.append(_case_result("Internet test reachability", "internet", "allow", ping(source, "hinternet", count=3)))
    if "hzalo" in CLUSTER_ALLOW_TARGETS[cluster]:
        cases.append(_case_result("Zalo service reachability", "internet", "allow", ping(source, "hzalo", count=3)))

    for target in CLUSTER_DENY_TARGETS[cluster]:
        cases.append(_case_result(f"Policy chặn {source} -> {target}", "segmentation", "deny", ping(source, target, count=2)))

    passed = sum(1 for item in cases if item["passed"])
    total = len(cases)
    score = round((passed / total) * 100, 1) if total else 0
    critical_failures = [
        item for item in cases
        if not item["passed"] and item["category"] in {"voice", "segmentation"}
    ]
    verdict = (
        "Đạt cho demo vận hành" if not critical_failures and score >= 80
        else "Chưa đạt: cần kiểm tra voice hoặc segmentation"
    )
    return {
        "ok": not critical_failures and score >= 80,
        "cluster": cluster,
        "source": source,
        "label": label,
        "score": score,
        "passed": passed,
        "total": total,
        "message": f"{label}: {verdict} ({passed}/{total}, {score}%).",
        "cases": cases,
        "verdict": verdict,
        "voice_estimation_note": (
            "Cfone/Gphone la softphone tren may agent; agent van nam trong VLAN du an. "
            "h90 dai dien PBX/SBC Voice Service. MOS/R-factor duoc uoc luong tu RTT, "
            "packet loss va jitter; khong phai cuoc goi SIP/RTP hoan chinh."
        ),
        "softphone_note": (
            "Cfono/Gphone là softphone cài trên máy agent: lab chỉ cho user VLAN đi tới "
            "cụm PBX/SBC/SIP-RTP và Call App cần thiết. Không mở ping ngang giữa "
            "Project/Telesale/BackOffice; chỉ IT Support có quyền remote/support có kiểm soát."
        ),
    }


def parse_flow_line(line: str, switch: str) -> dict[str, Any] | None:
    if "OFPST" in line or "NXST" in line:
        return None
    src_ip = re.search(r"(?:nw_src|ipv4_src)=([0-9./]+)", line)
    dst_ip = re.search(r"(?:nw_dst|ipv4_dst)=([0-9./]+)", line)
    priority = re.search(r"priority=(\d+)", line)
    cookie = re.search(r"cookie=0x([0-9a-fA-F]+)", line)
    packets = re.search(r"n_packets=(\d+)", line)
    byte_count = re.search(r"n_bytes=(\d+)", line)
    actions = line.split("actions=", 1)[1].strip() if "actions=" in line else ""
    source = _flow_match_label(src_ip.group(1) if src_ip else None)
    destination = _flow_match_label(dst_ip.group(1) if dst_ip else None)
    action = "DROP" if actions.lower() in {"", "drop"} else ("PACKET_IN" if "CONTROLLER" in actions else "ALLOW")
    reason = "Table-miss gửi gói mới lên controller."
    if source != "*" and destination != "*":
        decision = policy_decision(source, destination)
        reason = decision["reason"] if action != "DROP" or decision["action"] == "deny" else "Flow chặn tạm thời do người vận hành cài."
    return {
        "switch": switch,
        "source": source,
        "destination": destination,
        "src": source,
        "dst": destination,
        "action": action,
        "priority": int(priority.group(1)) if priority else 0,
        "cookie": f"0x{cookie.group(1)}" if cookie else "0x0",
        "match": f"{source} → {destination}",
        "raw_match": line.split("actions=", 1)[0].strip(),
        "raw_action": actions or "drop",
        "packets": int(packets.group(1)) if packets else 0,
        "bytes": int(byte_count.group(1)) if byte_count else 0,
        "reason": reason,
        "explanation": reason,
        "logical_device": switch,
    }


def ovs_flows() -> dict[str, Any]:
    flows = []
    raw_outputs = []
    live_switches = []
    for switch in CONTROLLED_SWITCHES:
        ok, output = mininet_control.dump_flows(switch)
        if not ok:
            continue
        live_switches.append(switch)
        raw_outputs.append(f"=== {switch} ===\n{output}")
        flows.extend(
            flow
            for line in output.splitlines()
            if (flow := parse_flow_line(line, switch)) is not None
        )
    if RUNTIME_FLOWS_FILE.exists():
        try:
            controller_flows = json.loads(RUNTIME_FLOWS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            controller_flows = []
    else:
        controller_flows = []
    return {
        "ok": bool(live_switches),
        "flows": flows,
        "controller_flows": controller_flows[-200:],
        "switches": live_switches,
        "logical_switches": list(CONTROLLED_SWITCHES),
        "runtime_switches": [runtime_switch_name(NETWORK_MODEL, switch) for switch in live_switches],
        "runtime_bridge_map": dict(RUNTIME_BRIDGE_MAP),
        "controller_status": "online" if len(live_switches) == len(CONTROLLED_SWITCHES) else "degraded" if live_switches else "unavailable",
        "raw": "\n\n".join(raw_outputs),
    }


def current_metrics() -> dict[str, Any]:
    payload = ovs_flows()
    metric_status = "live" if payload["ok"] else "unavailable"
    return {
        "timestamp": now_iso(),
        "live": payload["ok"],
        "status": metric_status,
        "data_source": "ovs_flow_counter" if payload["ok"] else None,
        "switches": payload["switches"],
        "flow_count": len(payload["flows"]),
        "packets": sum(flow["packets"] for flow in payload["flows"]),
        "bytes": sum(flow["bytes"] for flow in payload["flows"]),
        "flows": payload["flows"],
    }


def pair_flow_counters(source: str, destination: str, payload: dict[str, Any] | None = None) -> dict[str, int]:
    payload = payload if payload is not None else ovs_flows()
    total_bytes = 0
    total_packets = 0
    for flow in payload["flows"]:
        if (
            (flow.get("source") == source and flow.get("destination") == destination)
            or (flow.get("source") == destination and flow.get("destination") == source)
        ):
            total_bytes += int(flow.get("bytes") or 0)
            total_packets += int(flow.get("packets") or 0)
    return {"bytes": total_bytes, "packets": total_packets}


def pair_realtime_metrics(
    source: str,
    destination: str,
    previous_bytes: int | None = None,
    previous_time: float | None = None,
) -> dict[str, Any]:
    timestamp = time.time()
    ping_payload = ping(source, destination, count=2)
    result = ping_payload.get("result", {})
    flow_snapshot = ovs_flows()
    counters = pair_flow_counters(source, destination, flow_snapshot)
    byte_count = counters["bytes"]
    throughput_mbps = None
    if flow_snapshot.get("ok") and previous_bytes is not None and previous_time is not None and timestamp > previous_time:
        delta_bytes = max(0, byte_count - previous_bytes)
        throughput_mbps = round((delta_bytes * 8) / (timestamp - previous_time) / 1_000_000, 4)
    metric_status = "live" if counters["packets"] or ping_payload.get("ok") else "unavailable"
    return {
        "timestamp": now_iso(),
        "source": source,
        "destination": destination,
        "ok": bool(ping_payload.get("ok")),
        "delay_ms": result.get("rtt_avg_ms"),
        "packet_loss_percent": result.get("packet_loss_percent"),
        "jitter_ms": result.get("jitter_ms"),
        "throughput_mbps": throughput_mbps,
        "flow_packets": counters["packets"],
        "flow_bytes": byte_count,
        "byte_count": byte_count,
        "previous_byte_count": previous_bytes,
        "status": "monitoring",
        "metric_state": metric_status,
        "data_source": "mininet_ping_and_ovs_flow_counter" if metric_status == "live" else None,
        "message": ping_payload.get("message"),
        "decision": ping_payload.get("decision"),
    }


def manual_block_cookie(source: str, destination: str) -> int:
    key = "->".join(sorted((source, destination)))
    request_id = int(hashlib.sha1(key.encode("utf-8")).hexdigest()[:6], 16) % 0x6FFF
    return MANUAL_BLOCK_COOKIE_BASE + request_id


def manual_enforcement_switch(source: str, destination: str) -> str:
    decision = policy_decision(source, destination)
    blocked_at = decision.get("blocked_at")
    if blocked_at in CONTROLLED_SWITCHES:
        return str(blocked_at)
    source_data = ENGINE.endpoint(source)
    if source_data and source_data.get("kind") == "user":
        source_path = ENGINE.group_paths.get(str(source_data.get("group")), [])
        if source_path and source_path[-1] in CONTROLLED_SWITCHES:
            return str(source_path[-1])
    for node in reversed(decision.get("path", [])):
        switch = ENGINE.switches.get(str(node), {})
        if node in CONTROLLED_SWITCHES and switch.get("role") in {"hq_core", "branch_distribution"}:
            return str(node)
    destination_data = ENGINE.endpoint(destination)
    endpoint = source_data if source_data and source_data["kind"] == "user" else destination_data
    if endpoint and endpoint.get("kind") == "user":
        group_path = ENGINE.group_paths.get(str(endpoint.get("group")), [])
        if group_path and group_path[-1] in CONTROLLED_SWITCHES:
            return str(group_path[-1])
    raise ValueError(f"Khong tim thay enforcement switch cho {source} -> {destination}")


def temporary_block(source: str, destination: str, block: bool) -> dict[str, Any]:
    source_data = ENGINE.endpoint(source)
    destination_data = ENGINE.endpoint(destination)
    if not source_data or not destination_data:
        return {"ok": False, "message": "Nguồn hoặc đích không hợp lệ.", "raw": ""}
    outputs = []
    success = True
    switch = manual_enforcement_switch(source, destination)
    cookie = manual_block_cookie(source, destination)
    exists, output = mininet_control.bridge_exists(switch)
    if not exists:
        return {"ok": False, "message": f"Khong tim thay OVS enforcement {switch}.", "raw": output}
    if not block:
        ok, output = mininet_control.delete_cookie_flows(switch, cookie, COOKIE_MASK)
        return {
            "ok": ok,
            "message": f"Da go chan tam thoi {source} <-> {destination} tai {switch} bang cookie 0x{cookie:x}.",
            "raw": output,
        }
    for src_ip, dst_ip in ((source_data["ip"], destination_data["ip"]), (destination_data["ip"], source_data["ip"])):
        ok, output = mininet_control.add_manual_drop(switch, cookie, src_ip, dst_ip)
        success = success and ok
        outputs.append(output)
    verb = "chan" if block else "go chan"
    return {"ok": success, "message": f"Da {verb} tam thoi {source} <-> {destination} tai {switch} bang cookie 0x{cookie:x}.", "raw": "\n".join(outputs)}


def live_status() -> dict[str, Any]:
    status = mininet_control.live_status()
    if status.get("ok"):
        return status
    return {
        "ok": False,
        "available": False,
        "message": status.get("message", "Mininet control agent chua san sang."),
        "ovs_bridge": False,
        "bridges": {switch: False for switch in CONTROLLED_SWITCHES},
        "mnexec": command_exists("mnexec"),
        "iperf3": command_exists("iperf3"),
        "hosts": {name: False for name in ENGINE.hosts},
        "user_hosts_online": 0,
    }
