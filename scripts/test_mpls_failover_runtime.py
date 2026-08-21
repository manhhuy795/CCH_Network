#!/usr/bin/env python3
"""Validate MPLS primary/backup link failover using the live control agent."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.redesign_runtime_common import agent_request, ping, require_linux_root, verify_fabric, write_json


def main() -> int:
    try:
        require_linux_root()
        verify_fabric()
        baseline = ping("h50_01", "h90")
        down = agent_request("LINK_DOWN", link_id="ce_hq-mpls_primary")
        failover = ping("h50_01", "h90")
        recover = agent_request("LINK_UP", link_id="ce_hq-mpls_primary")
        restored = ping("h50_01", "h90")
        if not all(bool(item.get("ok")) for item in (baseline, down, failover, recover, restored)):
            raise RuntimeError("MPLS_FAILOVER_NOT_REACHABLE")
        report = {"ok": True, "baseline": baseline, "link_down": down, "failover": failover, "link_up": recover, "restored": restored}
        write_json(Path("runtime_reports/mpls_failover_runtime.json"), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"MPLS RUNTIME FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
