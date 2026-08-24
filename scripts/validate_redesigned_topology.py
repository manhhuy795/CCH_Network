#!/usr/bin/env python3
"""Validate the enterprise v7 source of truth without requiring Mininet."""

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
    user_count,
    validate_network_model,
)
from sdn_mpls_demo.policy_engine import PolicyEngine
from sdn_mpls_demo.runtime_contract import source_truth_runtime_links


ROOT = Path(__file__).resolve().parents[1]


def validate() -> list[str]:
    model = load_network_model()
    errors = list(validate_network_model(model))
    hosts = build_host_inventory(model)
    config = load_vars()

    if len(EXPECTED_CONTROLLED_SWITCHES) != 6:
        errors.append("v7 must expose exactly 6 controlled OVS")
    if len(EXPECTED_CE_NODES) != 4:
        errors.append("v7 must expose two CE nodes per physical site")
    if len(EXPECTED_FIREWALL_NODES) != 2:
        errors.append("v7 must expose one runtime firewall abstraction per site")
    if user_count(model) != 90:
        errors.append("runtime corporate user inventory must be exactly 90")

    vlan_by_id = {int(item["id"]): item for item in config["vlans"]}
    if set((50, 93, 101, 103, 104)) - set(vlan_by_id):
        errors.append("required v7 VLAN IDs are missing")
    vlan93 = vlan_by_id.get(93, {})
    if vlan93.get("subnet") != "10.10.93.0/24" or vlan93.get("gateway") != "10.10.93.1":
        errors.append("VLAN 93 addressing must be 10.10.93.0/24 with gateway 10.10.93.1")
    if vlan93.get("gateway_site") != "hq":
        errors.append("VLAN 93 gateway must be at HQ")

    routing_links = set(config.get("links", {}))
    expected_routed_links = {
        "hq_l3_to_ipsec",
        "ipsec_to_branch_l3",
        "hq_l3_to_fw_hq",
        "branch_l3_to_fw_branch",
        "fw_hq_to_internet_zone",
        "fw_branch_to_internet_zone",
    }
    if routing_links != expected_routed_links:
        errors.append(f"routing link inventory mismatch: {sorted(routing_links)}")

    try:
        runtime_links = source_truth_runtime_links(model)
    except ValueError as exc:
        errors.append(f"runtime link contract invalid: {exc}")
        runtime_links = []
    if not runtime_links:
        errors.append("runtime link contract is empty")

    policy = yaml.safe_load((ROOT / "sdn_mpls_demo/policy.yml").read_text(encoding="utf-8")) or {}
    if policy.get("dhcp", {}).get("relay_gateways") != ["core_hq", "dist_branch"]:
        errors.append("DHCP relay gateways must be core_hq and dist_branch")
    runtime_ipsec = policy.get("runtime", {}).get("ipsec_l3", {})
    if runtime_ipsec.get("cryptographic_ipsec") is not False:
        errors.append("runtime IPsec contract must explicitly state cryptographic_ipsec=false")

    engine = PolicyEngine(ROOT / "sdn_mpls_demo/policy.yml")
    expected_actions = {
        ("h93_01", "h93_11"): "allow",
        ("h101_01", "h103_01"): "deny",
        ("h101_01", "h90"): "allow",
        ("h101_01", "hsocial"): "deny",
        ("guest_01", "hinternet"): "allow",
        ("guest_01", "h93_01"): "deny",
        ("iot_branch_cam_01", "hmonitor"): "allow",
        ("iot_branch_cam_01", "h90"): "deny",
        ("h110_01", "h101_01"): "allow",
        ("h101_01", "h110_01"): "deny",
    }
    for pair, action in expected_actions.items():
        decision = engine.decide(*pair)
        if decision["action"] != action:
            errors.append(f"policy mismatch for {pair}: expected {action}, got {decision['action']}")

    l2_path = engine.decide("h93_11", "h93_01").get("path", [])
    if "l2vpn_primary" not in l2_path or "ipsec_l3" in l2_path:
        errors.append("cross-site VLAN 93 must use primary L2VPN and must not use IPsec")
    routed_path = engine.decide("iot_branch_cam_01", "hmonitor").get("path", [])
    if "ipsec_l3" not in routed_path or "l2vpn_primary" in routed_path:
        errors.append("Branch IoT to HQ monitoring must use routed ipsec_l3 abstraction")

    if len([item for item in hosts.values() if item["kind"] == "user"]) != 90:
        errors.append("expanded host inventory does not contain exactly 90 corporate users")
    return errors


def main() -> int:
    errors = validate()
    result = {"ok": not errors, "topology": "enterprise-v7", "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
