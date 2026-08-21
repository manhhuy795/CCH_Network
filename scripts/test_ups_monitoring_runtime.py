#!/usr/bin/env python3
"""Run real UPS-to-monitoring pings through the policy path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.redesign_runtime_common import ping, require_linux_root, verify_fabric, write_json


def main() -> int:
    try:
        require_linux_root()
        verify_fabric()
        cases = [(source, ping(source, "hmonitor")) for source in ("ups_floor1", "ups_core_1", "ups_branch_1")]
        if not all(bool(result.get("ok")) for _, result in cases):
            raise RuntimeError("UPS_MONITORING_PING_FAILED")
        report = {"ok": True, "cases": [{"source": source, "destination": "hmonitor", "result": result} for source, result in cases]}
        write_json(Path("runtime_reports/ups_monitoring_runtime.json"), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"UPS RUNTIME FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
