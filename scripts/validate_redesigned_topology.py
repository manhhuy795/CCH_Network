#!/usr/bin/env python3
"""Validate the redesigned topology and policy without requiring Ubuntu runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import load_vars
from scripts.network_model import (
    EXPECTED_CE_NODES,
    EXPECTED_CONTROLLED_SWITCHES,
    EXPECTED_FIREWALL_NODES,
    build_host_inventory,
    load_network_model,
    validate_network_model,
)
from sdn_mpls_demo.policy_engine import PolicyEngine


def validate() -> list[str]:
    errors = list(validate_network_model(load_network_model()))
    model = load_network_model()
    hosts = build_host_inventory(model)
    config = load_vars()
    if set(config["links"]) != {
        "core_hq_to_ce_hq", "ce_hq_to_mpls_primary", "mpls_primary_to_ce_telesale",
        "ce_hq_to_mpls_backup", "mpls_backup_to_ce_telesale", "ce_telesale_to_dist_branch",
        "core_hq_to_fw_hq", "dist_branch_to_fw_branch", "fw_hq_to_internet_zone",
        "fw_telesale_to_internet_zone",
    }:
        errors.append("transit link inventory is not the redesigned ten-link plan")
    if len(EXPECTED_CONTROLLED_SWITCHES) != 8 or len(EXPECTED_CE_NODES) != 2 or len(EXPECTED_FIREWALL_NODES) != 2:
        errors.append("redesign constants do not describe 8 OVS, 2 CE and 2 firewalls")
    if len([h for h in hosts.values() if h["kind"] == "user"]) != 110:
        errors.append("user inventory is not exactly 110")
    policy = yaml.safe_load((Path(__file__).resolve().parents[1] / "sdn_mpls_demo/policy.yml").read_text(encoding="utf-8"))
    if policy["dhcp"]["relay_gateways"] != ["core_hq", "dist_branch"]:
        errors.append("DHCP relay gateways must be core_hq and dist_branch")
    engine = PolicyEngine(Path(__file__).resolve().parents[1] / "sdn_mpls_demo/policy.yml")
    expected = {
        ("guest_01", "hinternet"): "allow", ("guest_01", "h20_01"): "deny",
        ("iot_cam_01", "hnvr"): "allow", ("iot_branch_cam_01", "hmonitor"): "allow",
        ("h50_01", "h90"): "allow", ("h20_01", "hsocial"): "deny",
    }
    for pair, action in expected.items():
        if engine.decide(*pair)["action"] != action:
            errors.append(f"policy mismatch for {pair}: expected {action}")
    return errors


def main() -> int:
    errors = validate()
    result = {"ok": not errors, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
