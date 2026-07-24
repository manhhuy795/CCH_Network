#!/usr/bin/env python3
"""Run the required real data-flow ping cases against Mininet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.redesign_runtime_common import ping, require_linux_root, verify_fabric, write_json


CASES = (
    ("guest_01", "hinternet", True), ("guest_01", "h20_01", False),
    ("iot_cam_01", "hnvr", True), ("iot_branch_cam_01", "hmonitor", True),
    ("h50_01", "h90", True), ("h50_01", "hdialer", True),
    ("h60_01", "h90", True), ("h20_01", "hsocial", False),
)


def main() -> int:
    try:
        require_linux_root()
        verify_fabric()
        results = []
        for source, destination, expected in CASES:
            response = ping(source, destination)
            actual = bool(response.get("ok"))
            results.append({"source": source, "destination": destination, "expected": expected, "actual": actual, "result": response})
            if actual != expected:
                raise RuntimeError(f"DATA_FLOW_POLICY_MISMATCH:{source}->{destination}")
        report = {"ok": True, "cases": results}
        write_json(Path("runtime_reports/data_flows_runtime.json"), report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"DATA FLOW RUNTIME FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
