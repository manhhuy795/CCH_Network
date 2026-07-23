#!/usr/bin/env python3
"""Static security audit for the current two-site Call Center lab.

This script checks policy intent and source-of-truth only. It never reports
live OVS, nftables or ping success; use infrastructure_security_runtime_check.sh
on Ubuntu for runtime evidence.
"""

from __future__ import annotations

import ipaddress
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.common import load_vars
from scripts.network_model import build_host_inventory, controlled_switches, load_network_model, validate_network_model
from sdn_mpls_demo.policy_engine import PolicyEngine


@dataclass(frozen=True)
class SecurityCase:
    name: str
    source: str
    destination: str
    expected_action: str
    expected_blocked_at: str | None


SECURITY_CASES = (
    SecurityCase("Project A to Project B isolation", "h20_01", "h30_01", "deny", "core_hq"),
    SecurityCase("Project A to Project C isolation", "h20_01", "h40_01", "deny", "core_hq"),
    SecurityCase("Telesale to BackOffice isolation", "h50_01", "h60_01", "deny", "dist_telesale"),
    SecurityCase("BackOffice to Telesale isolation", "h60_01", "h50_01", "deny", "core_hq"),
    SecurityCase("Project A to Voice", "h20_01", "h90", "allow", None),
    SecurityCase("Telesale to Voice through MPLS", "h50_01", "h90", "allow", None),
    SecurityCase("IT to Project A management", "h70_01", "h20_01", "allow", None),
    SecurityCase("Regular user to IT denied", "h20_01", "h70_01", "deny", "core_hq"),
    SecurityCase("IT cannot bypass Social Media block", "h70_01", "hsocial", "deny", "fw_hq"),
    SecurityCase("Project Social Media block", "h20_01", "hsocial", "deny", "fw_hq"),
    SecurityCase("Internet inbound to HQ user", "hinternet", "h20_01", "deny", "fw_hq"),
    SecurityCase("Internet inbound to branch user", "hsocial", "h50_01", "deny", "fw_telesale"),
)


def audit() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        results.append((name, bool(passed), detail))

    model = load_network_model()
    config = load_vars()
    hosts = build_host_inventory(model)
    engine = PolicyEngine(ROOT_DIR / "sdn_mpls_demo" / "policy.yml")

    errors = validate_network_model(model)
    add("network model validation", not errors, "; ".join(errors) or "valid")

    vlan_ids = [int(item["id"]) for item in config.get("vlans", [])]
    add("VLAN identifiers unique", len(vlan_ids) == len(set(vlan_ids)), str(vlan_ids))
    add("management VLAN 10 exists", 10 in vlan_ids, "VLAN 10 is reserved for management/NMS")
    add("user subnets do not overlap", _non_overlapping([item["subnet"] for item in model["host_groups"].values()]), "host group CIDRs")
    add("endpoint IPs unique", len({host["ip"] for host in hosts.values()}) == len(hosts), "110 users and 5 services")
    add("inventory count", len(hosts) == 115 and sum(host["kind"] == "user" for host in hosts.values()) == 110, str(len(hosts)))
    add("controlled OVS count", len(controlled_switches(model)) == 9, str(controlled_switches(model)))

    firewall_policy = config.get("firewall_policy", {})
    defaults = firewall_policy.get("runtime_defaults", {})
    add("firewall forward default drop", defaults.get("forward_policy") == "drop", str(defaults.get("forward_policy")))
    add("firewall input default drop", defaults.get("input_policy") == "drop", str(defaults.get("input_policy")))
    add("stateful established handling", defaults.get("allow_established_related") is True, str(defaults.get("allow_established_related")))
    add("invalid packet drop", defaults.get("drop_invalid") is True, str(defaults.get("drop_invalid")))
    add("firewall counters enabled", defaults.get("counter_enabled") is True, str(defaults.get("counter_enabled")))
    add("NAT not silently assumed", defaults.get("nat", {}).get("enabled") is False, str(defaults.get("nat", {})))

    for site, inside, outside in (("hq", "core_hq", "internet_zone"), ("branch_telesale", "dist_telesale", "internet_zone")):
        site_policy = firewall_policy.get("sites", {}).get(site, {})
        add(f"{site} firewall inside endpoint", site_policy.get("inside_node") == inside, str(site_policy.get("inside_node")))
        add(f"{site} firewall outside endpoint", site_policy.get("outside_node") == outside, str(site_policy.get("outside_node")))
        interfaces = site_policy.get("runtime_interfaces", {})
        add(f"{site} firewall inside/outside interfaces", bool(interfaces.get("inside") and interfaces.get("outside")), str(interfaces))

    isolation_specs = engine.isolation_flow_specs()
    add("SDN isolation enforcement placement", {spec["switch"] for spec in isolation_specs} == {"core_hq", "dist_telesale"}, str({spec["switch"] for spec in isolation_specs}))
    add("SDN isolation uses drop", all(spec["action"] == "DROP" for spec in isolation_specs), str({spec["action"] for spec in isolation_specs}))
    add("SDN isolation priority", all(spec["priority"] == 400 for spec in isolation_specs), str({spec["priority"] for spec in isolation_specs}))

    paths = {}
    for case in SECURITY_CASES:
        decision = engine.decide(case.source, case.destination)
        paths[case.name] = decision.get("path") or []
        passed = decision.get("action") == case.expected_action and decision.get("blocked_at") == case.expected_blocked_at
        detail = f"action={decision.get('action')} blocked_at={decision.get('blocked_at')} path={' -> '.join(paths[case.name])}"
        add(f"policy: {case.name}", passed, detail)

    add("Voice path bypasses Internet firewall", "fw_hq" not in paths["Project A to Voice"] and "fw_telesale" not in paths["Telesale to Voice through MPLS"], str({name: path for name, path in paths.items() if "Voice" in name}))
    add("Inbound service path reaches firewall", "fw_hq" in paths["Internet inbound to HQ user"] and "fw_telesale" in paths["Internet inbound to branch user"], str({name: path for name, path in paths.items() if "inbound" in name.lower()}))

    controller_source = (ROOT_DIR / "sdn_mpls_demo" / "controller_policy.py").read_text(encoding="utf-8")
    add("controller uses OpenFlow 1.3", "ofproto_v1_3.OFP_VERSION" in controller_source, "controller_policy.py")
    add("access switches are transit only", "Khong cai isolation DROP tren %s; access OVS chi transit/local switching." in controller_source, "no access-side isolation DROP")

    return results


def _non_overlapping(values: list[str]) -> bool:
    networks = [ipaddress.ip_network(value, strict=False) for value in values]
    return all(not left.overlaps(right) for index, left in enumerate(networks) for right in networks[index + 1 :])


def main() -> int:
    print("INFRASTRUCTURE SECURITY SOURCE AUDIT (STATIC; LIVE RUNTIME NOT CLAIMED)")
    results = audit()
    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL':4} {name}: {detail}")
    passed_count = sum(passed for _name, passed, _detail in results)
    print(f"RESULT {passed_count}/{len(results)} STATIC CHECKS PASS")
    print("RUNTIME STATUS: PENDING UBUNTU - run sudo ./scripts/infrastructure_security_runtime_check.sh")
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
