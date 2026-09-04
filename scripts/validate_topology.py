#!/usr/bin/env python3
"""Small non-Mininet smoke check for the enterprise Full-SDN topology."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import load_vars
from scripts.network_model import load_network_model
from scripts.validate_vars import validate_all
from sdn_mpls_demo.policy_engine import PolicyEngine
from sdn_mpls_demo.runtime_contract import source_truth_runtime_links


ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / "sdn_mpls_demo" / "policy.yml"


def validate() -> list[str]:
    errors = validate_all(load_vars())
    model = load_network_model()

    try:
        if not source_truth_runtime_links(model):
            errors.append("runtime link contract is empty")
    except ValueError as exc:
        errors.append(f"runtime link contract invalid: {exc}")

    engine = PolicyEngine(POLICY_FILE)
    smoke = {
        ("h93_01", "h93_11"): "allow",
        ("h101_01", "h103_01"): "deny",
        ("guest_01", "h93_01"): "deny",
        ("iot_branch_cam_01", "hmonitor"): "allow",
    }
    for pair, expected in smoke.items():
        decision = engine.decide(*pair)
        if decision["action"] != expected:
            errors.append(f"policy mismatch for {pair}: expected {expected}, got {decision['action']}")

    l2_path = engine.decide("h93_11", "h93_01").get("path", [])
    if "l2vpn_primary" not in l2_path or "ipsec_l3" in l2_path:
        errors.append("VLAN 93 must use L2VPN, not IPsec")

    routed_path = engine.decide("iot_branch_cam_01", "hmonitor").get("path", [])
    required = ["dist_branch", "fw_telesale", "ipsec_l3", "fw_hq", "core_hq"]
    try:
        indexes = [routed_path.index(node) for node in required]
    except ValueError:
        indexes = []
    if not indexes or indexes != sorted(indexes) or "l2vpn_primary" in routed_path:
        errors.append("Branch routed traffic must traverse Branch firewall -> ipsec_l3 -> HQ firewall")
    return errors


def main() -> int:
    errors = validate()
    print(json.dumps({"ok": not errors, "topology": "enterprise-v7", "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
