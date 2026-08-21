#!/usr/bin/env python3
"""Verify DHCP relay live evidence; static addressing is never reported as a lease."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.redesign_runtime_common import agent_request, require_linux_root, write_json


def main() -> int:
    try:
        require_linux_root()
        live = agent_request("LIVE_STATUS")
        if live.get("ok") is not True:
            raise RuntimeError("AGENT_NOT_READY")
        # The current deterministic lab assigns reserved addresses. A real DHCP
        # lease must be evidenced by a DHCP server/lease record, not by host IP.
        report = {"ok": False, "status": "PENDING", "reason": "DHCP live lease server/relay evidence is not implemented in this Mininet profile.", "live": live}
        write_json(Path("runtime_reports/dhcp_runtime.json"), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        print(f"DHCP RUNTIME FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
