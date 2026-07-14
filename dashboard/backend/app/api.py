from __future__ import annotations

from fastapi import APIRouter, Request

from .live_mininet import cluster_detail_test, current_metrics, live_status, ovs_flows, pair_realtime_metrics, policy_decision, temporary_block
from .metrics import run_call_quality, run_iperf, run_ping
from .models import ClusterTestRequest, HostPair, IperfRequest, LinkStateRequest, LinkUpdateRequest, PolicyToggleRequest
from .policy import get_policy_payload, toggle_policy
from .topology import get_topology


router = APIRouter(prefix="/api")


def failed_links(request: Request) -> set[str]:
    if not hasattr(request.app.state, "failed_links"):
        request.app.state.failed_links = set()
    return request.app.state.failed_links


@router.get("/topology")
def api_topology(request: Request):
    return get_topology(failed_links(request))


@router.get("/policies")
def api_policies():
    return get_policy_payload()


@router.get("/flows")
def api_flows(request: Request):
    return ovs_flows()


@router.get("/metrics/current")
def api_metrics_current(request: Request):
    return current_metrics()


@router.post("/metrics/pair")
def api_metrics_pair(payload: HostPair):
    return pair_realtime_metrics(payload.source, payload.destination)


@router.get("/live/status")
def api_live_status():
    return live_status()


@router.post("/test/ping")
def api_test_ping(payload: HostPair, request: Request):
    return run_ping(payload.source, payload.destination, failed_links(request))


@router.post("/test/iperf")
def api_test_iperf(payload: IperfRequest, request: Request):
    return run_iperf(payload.source, payload.destination, payload.protocol, payload.seconds, failed_links(request))


@router.post("/test/call-quality")
def api_test_call_quality(payload: IperfRequest, request: Request):
    return run_call_quality(payload.source, payload.destination, payload.seconds, failed_links(request))


@router.post("/test/cluster-detail")
def api_test_cluster_detail(payload: ClusterTestRequest):
    return cluster_detail_test(payload.cluster, payload.seconds)


@router.post("/live/block")
def api_live_block(payload: HostPair):
    return temporary_block(payload.source, payload.destination, block=True)


@router.post("/live/unblock")
def api_live_unblock(payload: HostPair):
    return temporary_block(payload.source, payload.destination, block=False)


@router.post("/policy/apply")
def api_policy_apply():
    return {"ok": False, "message": "Dung /api/policy/toggle de ghi policy.yml atomic va yeu cau controller reload."}


@router.post("/policy/toggle")
def api_policy_toggle(payload: PolicyToggleRequest):
    try:
        return toggle_policy(payload.key, payload.enabled)
    except (KeyError, ValueError) as exc:
        return {"ok": False, "message": str(exc)}


@router.post("/simulate/path")
def api_simulate_path(payload: HostPair, request: Request):
    decision = policy_decision(payload.source, payload.destination)
    path = decision.get("path", [])
    failed = failed_links(request)
    for index, (left, right) in enumerate(zip(path, path[1:])):
        if f"{left}-{right}" in failed or f"{right}-{left}" in failed:
            return {
                "src": payload.source,
                "dst": payload.destination,
                "action": "deny",
                "reason": "Khong co duong di hop le do lien ket dang bi loi.",
                "path": path[: index + 1],
                "blocked_at": left,
                "failed_link": f"{left}-{right}",
                "mode": "logical_architecture",
            }
    return {
        "src": payload.source,
        "dst": payload.destination,
        **decision,
        "mode": "logical_architecture",
        "note": "Duong logic phuc vu minh hoa; ket qua ping/iperf van lay truc tiep tu Mininet/OVS.",
    }


@router.post("/link/update")
def api_link_update(payload: LinkUpdateRequest):
    return {"ok": True, "message": "Co the thay doi bandwidth/delay/loss bang TCLink trong Mininet.", "link": payload.model_dump()}


@router.post("/link/fail")
def api_link_fail(payload: LinkStateRequest, request: Request):
    failed_links(request).add(payload.link_id)
    return {"ok": True, "message": f"Da mo phong loi lien ket {payload.link_id}.", "failed_links": sorted(failed_links(request))}


@router.post("/link/recover")
def api_link_recover(payload: LinkStateRequest, request: Request):
    failed_links(request).discard(payload.link_id)
    return {"ok": True, "message": f"Da khoi phuc lien ket {payload.link_id}.", "failed_links": sorted(failed_links(request))}
