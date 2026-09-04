#!/usr/bin/env python3
"""Validate MPLS primary/backup link failover using the live control agent."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.runtime_common import agent_request, command, ping, require_linux_root, verify_fabric, write_json


def flow(switch: str) -> str:
    return command(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", switch, "table=30"]).stdout


def main() -> int:
    try:
        require_linux_root()
        verify_fabric()
        baseline = ping("h93_01", "h93_11", count=3)
        primary_flows = {switch: flow(switch) for switch in ("core_hq", "dist_branch")}
        down = agent_request("LINK_DOWN", link_id="core_hq-ce_hq1")
        time.sleep(10)
        ping("h93_01", "h93_11", count=1)
        failover = ping("h93_01", "h93_11", count=5)
        backup_flows = {switch: flow(switch) for switch in ("core_hq", "dist_branch")}
        recover = agent_request("LINK_UP", link_id="core_hq-ce_hq1")
        time.sleep(10)
        ping("h93_01", "h93_11", count=1)
        restored = ping("h93_01", "h93_11", count=5)
        restored_flows = {switch: flow(switch) for switch in ("core_hq", "dist_branch")}
        if not all(bool(item.get("ok")) for item in (baseline, down, failover, recover, restored)):
            raise RuntimeError(
                "MPLS_FAILOVER_NOT_REACHABLE:"
                + json.dumps(
                    {"baseline": baseline, "down": down, "failover": failover, "recover": recover, "restored": restored},
                    ensure_ascii=False,
                )
            )
        report = {
            "ok": True,
            "baseline": baseline,
            "link_down": down,
            "failover": failover,
            "link_up": recover,
            "restored": restored,
            "primary_flows": primary_flows,
            "backup_flows": backup_flows,
            "restored_flows": restored_flows,
        }
        write_json(Path("runtime_reports/mpls_failover_runtime.json"), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"MPLS RUNTIME FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
