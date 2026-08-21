#!/usr/bin/env python3
"""Collect a small, repeatable Mininet evidence set for the dashboard.

The report only contains observations from the live control-agent socket and
Open vSwitch.  It deliberately avoids synthetic time-series data so the UI can
show what was actually measured when the demo started.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.redesign_runtime_common import agent_request, model_hosts, ping, require_linux_root, verify_fabric


ROOT = Path(__file__).resolve().parents[1]
REPORT_FILE = ROOT / "runtime_reports" / "dashboard_preflight.json"
CASES = (
    {
        "id": "vlan40_hq_to_branch",
        "label": "VLAN 40 · HQ → Branch",
        "source": "h40_01",
        "destination": "h40_11",
        "expected": True,
        "evidence": "VPWS/E-Line forward path",
    },
    {
        "id": "vlan40_branch_to_hq",
        "label": "VLAN 40 · Branch → HQ",
        "source": "h40_11",
        "destination": "h40_01",
        "expected": True,
        "evidence": "VPWS/E-Line return path",
    },
    {
        "id": "branch_voice_to_pbx",
        "label": "Telesale → PBX/SBC",
        "source": "h50_01",
        "destination": "h90",
        "expected": True,
        "evidence": "Voice service reachability",
    },
    {
        "id": "project_segmentation",
        "label": "Project C ↛ Project B",
        "source": "h40_01",
        "destination": "h30_01",
        "expected": False,
        "evidence": "Inter-project isolation",
    },
    {
        "id": "guest_isolation",
        "label": "Guest ↛ Project C",
        "source": "guest_01",
        "destination": "h40_01",
        "expected": False,
        "evidence": "Guest isolation",
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ping_output(raw: str) -> dict[str, float | None]:
    loss_match = re.search(r"([0-9]+(?:\.[0-9]+)?)% packet loss", raw)
    rtt_match = re.search(
        r"(?:rtt|round-trip) min/avg/max/(?:mdev|stddev) = "
        r"[0-9.]+/([0-9.]+)/[0-9.]+/[0-9.]+ ms",
        raw,
    )
    return {
        "packet_loss_percent": float(loss_match.group(1)) if loss_match else None,
        "avg_rtt_ms": float(rtt_match.group(1)) if rtt_match else None,
    }


def write_report(payload: dict[str, Any]) -> None:
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(REPORT_FILE)


def collect_report() -> dict[str, Any]:
    started = time.monotonic()
    fabric = verify_fabric()
    link_response = agent_request("GET_LINK_STATUS")
    link_states = dict(link_response.get("links") or {})
    down_links = sorted(name for name, state in link_states.items() if state != "up")
    if link_response.get("ok") is not True or down_links:
        raise RuntimeError(f"LINK_STATE_INVALID:{','.join(down_links) or 'unavailable'}")
    inventory = model_hosts()
    case_results: list[dict[str, Any]] = []

    for case in CASES:
        response = ping(str(case["source"]), str(case["destination"]), count=2)
        reachable = bool(response.get("ok"))
        expected = bool(case["expected"])
        measurements = parse_ping_output(str(response.get("raw") or ""))
        case_results.append({
            **case,
            "expectation": "allow" if expected else "deny",
            "observed": "reachable" if reachable else "blocked",
            "passed": reachable is expected,
            "duration_seconds": response.get("duration_seconds"),
            **measurements,
        })

    flow_counts = {
        str(name): int(count)
        for name, count in dict(fabric.get("flow_counts") or {}).items()
    }
    live = dict(fabric.get("live") or {})
    hosts = dict(live.get("hosts") or {})
    passed = sum(bool(item["passed"]) for item in case_results)
    return {
        "schema_version": 1,
        "status": "passed" if passed == len(case_results) else "failed",
        "checked_at": utc_now(),
        "duration_seconds": round(time.monotonic() - started, 3),
        "source": "Mininet Control Agent + ovs-ofctl OpenFlow13",
        "summary": {
            "checks_passed": passed,
            "checks_total": len(case_results),
            "endpoints_online": sum(bool(value) for value in hosts.values()),
            "endpoints_total": len(inventory),
            "user_hosts_online": int(live.get("user_hosts_online") or 0),
            "switches_ready": len(flow_counts),
            "switches_expected": len(flow_counts),
            "flow_entries": sum(flow_counts.values()),
            "links_up": sum(state == "up" for state in link_states.values()),
            "links_total": len(link_states),
        },
        "flow_counts": flow_counts,
        "cases": case_results,
    }


def main() -> int:
    try:
        require_linux_root()
        report = collect_report()
    except Exception as exc:
        report = {
            "schema_version": 1,
            "status": "failed",
            "checked_at": utc_now(),
            "duration_seconds": 0,
            "source": "Mininet Control Agent + ovs-ofctl OpenFlow13",
            "summary": {"checks_passed": 0, "checks_total": len(CASES)},
            "flow_counts": {},
            "cases": [],
            "error_code": type(exc).__name__,
            "message": str(exc),
        }
        write_report(report)
        print(f"PREFLIGHT FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    write_report(report)
    summary = report["summary"]
    print(
        "PREFLIGHT "
        f"{report['status'].upper()} · checks {summary['checks_passed']}/{summary['checks_total']} · "
        f"endpoints {summary['endpoints_online']}/{summary['endpoints_total']} · "
        f"flows {summary['flow_entries']}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
