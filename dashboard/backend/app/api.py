from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from . import mininet_control
from .errors import ERROR_HTTP_STATUS
from .live_mininet import cluster_detail_test, current_metrics, enrich_decision, iperf_runtime_status, live_status, ovs_flows, pair_realtime_metrics, policy_decision, temporary_block
from .metrics import run_call_quality, run_iperf, run_ping
from .models import ClusterTestRequest, HostPair, IperfRequest, LinkStateRequest, LinkUpdateRequest, PolicyToggleRequest
from .policy import get_policy_payload, toggle_policy
from .security import auth_status, require_operator
from .topology import get_topology
from .runtime_health import live_health_payload, system_health


router = APIRouter(prefix="/api")
operator_required = Depends(require_operator)


def _normalize_operation_error(payload: dict) -> dict:
    result = dict(payload)
    code = str(result.get("error_code") or "")
    infrastructure_codes = {
        "MININET_NOT_RUNNING",
        "AGENT_NOT_READY",
        "AGENT_TIMEOUT",
        "AGENT_DISCONNECTED",
        "CONTROLLER_OFFLINE",
        "OVS_UNAVAILABLE",
    }
    if (
        result.get("decision", {}).get("action") == "deny"
        and not result.get("ok")
        and code not in infrastructure_codes
    ):
        code = "POLICY_DENIED"
    elif code in {"IPERF_DESTINATION_BUSY", "IPERF_CONCURRENCY_LIMIT"}:
        code = "IPERF_BUSY"
    elif code in {"IPERF_SERVER_NOT_LISTENING", "IPERF_SERVER_START_FAILED"}:
        code = "IPERF_SERVER_FAILED"
    elif code in {"IPERF_CLIENT_ERROR"}:
        code = "IPERF_CLIENT_FAILED"
    elif code in {"IPERF_JSON_INVALID"} or result.get("parse_warning"):
        code = "IPERF_PARSE_FAILED"
    if code:
        result["error_code"] = code
    result.setdefault("message_vi", str(result.get("message") or "Tac vu hoan thanh."))
    return result


def operation_response(payload: dict) -> dict | JSONResponse:
    normalized = _normalize_operation_error(payload)
    code = str(normalized.get("error_code") or "")
    if normalized.get("ok") or normalized.get("measurement_completed") or code == "POLICY_DENIED":
        return normalized
    status_code = ERROR_HTTP_STATUS.get(code, 503)
    return JSONResponse(status_code=status_code, content=normalized)


def failed_link_ids() -> list[str]:
    status = mininet_control.get_link_status()
    if not status.get("ok"):
        return []
    return sorted(
        link_id
        for link_id, state in status.get("links", {}).items()
        if state == "down"
    )


@router.get("/topology")
def api_topology():
    return get_topology()


@router.get("/auth/status")
def api_auth_status():
    return auth_status()


@router.get("/policies")
def api_policies():
    return get_policy_payload()


@router.get("/flows")
def api_flows(request: Request):
    return ovs_flows()


@router.get("/metrics/current")
def api_metrics_current(request: Request):
    return current_metrics()


@router.post("/metrics/pair", dependencies=[operator_required])
def api_metrics_pair(payload: HostPair):
    return pair_realtime_metrics(payload.source, payload.destination)


@router.get("/live/status")
def api_live_status():
    return {**live_health_payload(), "iperf_sessions": iperf_runtime_status()}


@router.get("/live/iperf-sessions", dependencies=[operator_required])
def api_live_iperf_sessions():
    return iperf_runtime_status()


@router.get("/health")
def api_health():
    return system_health()


@router.post("/test/ping", dependencies=[operator_required])
def api_test_ping(payload: HostPair):
    return operation_response(run_ping(payload.source, payload.destination))


@router.post("/test/iperf", dependencies=[operator_required])
def api_test_iperf(payload: IperfRequest):
    return operation_response(run_iperf(payload.source, payload.destination, payload.protocol, payload.seconds))


@router.post("/test/call-quality", dependencies=[operator_required])
def api_test_call_quality(payload: IperfRequest):
    return operation_response(run_call_quality(payload.source, payload.destination, payload.seconds))


@router.post("/test/cluster-detail", dependencies=[operator_required])
def api_test_cluster_detail(payload: ClusterTestRequest):
    return cluster_detail_test(payload.cluster, payload.seconds)


@router.post("/live/block", dependencies=[operator_required])
def api_live_block(payload: HostPair):
    return temporary_block(payload.source, payload.destination, block=True)


@router.post("/live/unblock", dependencies=[operator_required])
def api_live_unblock(payload: HostPair):
    return temporary_block(payload.source, payload.destination, block=False)


@router.post("/policy/apply", dependencies=[operator_required])
def api_policy_apply():
    return {"ok": False, "message": "Dung /api/policy/toggle de ghi policy.yml atomic va yeu cau controller reload."}


@router.post("/policy/toggle", dependencies=[operator_required])
def api_policy_toggle(payload: PolicyToggleRequest):
    try:
        return toggle_policy(payload.key, payload.enabled)
    except (KeyError, ValueError) as exc:
        return {"ok": False, "message": str(exc)}


@router.post("/simulate/path", dependencies=[operator_required])
def api_simulate_path(payload: HostPair):
    decision = policy_decision(payload.source, payload.destination)
    path = decision.get("path", [])
    down = mininet_control.first_down_link(path)
    if down:
        failed_link = down["link_id"]
        blocked_at = down["blocked_at"]
        stop_index = path.index(blocked_at) if blocked_at in path else 0
        decision = {
            **decision,
            "action": "deny",
            "reason": "Khong co duong di hop le do lien ket that trong Mininet dang down.",
            "path": path[: stop_index + 1],
            "blocked_at": blocked_at,
            "failed_link": failed_link,
        }
        return {
            "src": payload.source,
            "dst": payload.destination,
            **enrich_decision(payload.source, payload.destination, decision),
            "mode": "logical_architecture",
        }
    return {
        "src": payload.source,
        "dst": payload.destination,
        **enrich_decision(payload.source, payload.destination, decision),
        "mode": "logical_architecture",
        "note": "Duong logic phuc vu minh hoa; ket qua ping/iperf van lay truc tiep tu Mininet/OVS.",
    }


@router.post("/link/update", dependencies=[operator_required])
def api_link_update(payload: LinkUpdateRequest):
    return {"ok": True, "message": "Co the thay doi bandwidth/delay/loss bang TCLink trong Mininet.", "link": payload.model_dump()}


@router.post("/link/fail", dependencies=[operator_required])
def api_link_fail(payload: LinkStateRequest):
    result = mininet_control.set_link_state(payload.link_id, "down")
    result["failed_links"] = failed_link_ids()
    return result


@router.post("/link/recover", dependencies=[operator_required])
def api_link_recover(payload: LinkStateRequest):
    result = mininet_control.set_link_state(payload.link_id, "up")
    result["failed_links"] = failed_link_ids()
    return result
