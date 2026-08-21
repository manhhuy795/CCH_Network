#!/usr/bin/env python3
"""Run real Mininet/OVS checks for the redesigned topology."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.redesign_runtime_common import ping, require_linux_root, verify_fabric, write_json


CASES = (
    ("guest_internet_allow", "guest_01", "hinternet", True),
    ("guest_project_deny", "guest_01", "h20_01", False),
    ("iot_hq_nvr_allow", "iot_cam_01", "hnvr", True),
    ("iot_branch_monitoring_allow", "iot_branch_cam_01", "hmonitor", True),
    ("telesale_voice_allow", "h50_01", "h90", True),
    ("project_isolation_deny", "h20_01", "h30_01", False),
)


def main() -> int:
    try:
        require_linux_root()
        fabric = verify_fabric()
        results = []
        for name, source, destination, expected in CASES:
            response = ping(source, destination)
            actual = bool(response.get("ok"))
            results.append({"case": name, "source": source, "destination": destination, "expected": expected, "actual": actual, "raw": response.get("raw", "")})
            if actual != expected:
                raise RuntimeError(f"{name}: expected {expected}, actual {actual}")
        report = {"checked_at": datetime.now(timezone.utc).isoformat(), "fabric": fabric, "cases": results, "ok": True}
        path = Path("runtime_reports/redesigned_topology_runtime.json")
        write_json(path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"RUNTIME FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
