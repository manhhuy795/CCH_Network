from __future__ import annotations

from fastapi import APIRouter, Request

from .live_mininet import current_metrics, live_status, ovs_flows, temporary_block
from .metrics import run_iperf, run_ping
from .models import HostPair, IperfRequest, LinkStateRequest, LinkUpdateRequest, PolicyToggleRequest
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


@router.get("/live/status")
def api_live_status():
    return live_status()


@router.post("/test/ping")
def api_test_ping(payload: HostPair, request: Request):
    return run_ping(payload.source, payload.destination, failed_links(request))


@router.post("/test/iperf")
def api_test_iperf(payload: IperfRequest, request: Request):
    return run_iperf(payload.source, payload.destination, payload.protocol, payload.seconds, failed_links(request))


@router.post("/live/block")
def api_live_block(payload: HostPair):
    return temporary_block(payload.source, payload.destination, block=True)


@router.post("/live/unblock")
def api_live_unblock(payload: HostPair):
    return temporary_block(payload.source, payload.destination, block=False)


@router.post("/policy/apply")
def api_policy_apply():
    return {"ok": True, "message": "Policy file nam trong sdn_demo/policy.yml. Controller doc policy khi restart."}


@router.post("/policy/toggle")
def api_policy_toggle(payload: PolicyToggleRequest):
    try:
        policies = toggle_policy(payload.key, payload.enabled)
        return {"ok": True, "message": "Da cap nhat trang thai hien thi policy tren dashboard.", "policies": policies}
    except KeyError as exc:
        return {"ok": False, "message": str(exc)}


@router.post("/simulate/path")
def api_simulate_path(payload: HostPair, request: Request):
    return {
        "src": payload.source,
        "dst": payload.destination,
        "action": "live",
        "reason": "Dashboard dang dung ket qua that tu Mininet. Hay bam Ping hoac Iperf de xem output that.",
        "path": [payload.source, "s1", payload.destination],
    }


@router.post("/link/update")
def api_link_update(payload: LinkUpdateRequest):
    return {"ok": True, "message": "Ban co the thay doi bandwidth/delay bang tc trong Mininet neu can.", "link": payload.model_dump()}


@router.post("/link/fail")
def api_link_fail(payload: LinkStateRequest, request: Request):
    failed_links(request).add(payload.link_id)
    return {"ok": True, "message": f"Da danh dau link {payload.link_id} tren dashboard.", "failed_links": sorted(failed_links(request))}


@router.post("/link/recover")
def api_link_recover(payload: LinkStateRequest, request: Request):
    failed_links(request).discard(payload.link_id)
    return {"ok": True, "message": f"Da khoi phuc link {payload.link_id} tren dashboard.", "failed_links": sorted(failed_links(request))}
