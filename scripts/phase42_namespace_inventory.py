#!/usr/bin/env python3
"""Classify live Mininet process names for the Phase 42 resource gate."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable


EXPECTED_SERVICES = frozenset({"h90", "hzalo", "hcall", "hsocial", "hinternet"})
EXPECTED_INFRA_NAMESPACES = frozenset(
    {
        "ce_hq", "ce_telesale", "fw_hq", "fw_telesale", "mpls_primary", "mpls_backup", "internet_zone",
        "hdhcp", "hdns", "hntp", "hmonitor", "hnvr", "hrecording", "hdialer", "hbackup", "had",
    }
)
EXPECTED_ENTERPRISE_ENDPOINTS = frozenset({
    "iot_cam_01", "iot_cam_02", "ups_floor1", "ups_core_1", "ups_core_2",
    "iot_branch_cam_01", "ups_branch_1", "guest_01", "guest_02",
})
KNOWN_NON_SERVICE_NODES = frozenset({"hq_l3_gateway", "telesale_l3_gateway", "service_net"})
USER_COUNTS = {20: 20, 30: 20, 40: 20, 50: 20, 60: 20, 70: 10}
EXPECTED_USERS = frozenset(
    f"h{vlan}_{index:02d}"
    for vlan, count in USER_COUNTS.items()
    for index in range(1, count + 1)
)

MININET_NAME_PATTERN = re.compile(r"mininet:([^\s]+)")
USER_NAME_PATTERN = re.compile(r"^h(?:20|30|40|50|60|70)_\d{2}$")
SERVICE_LIKE_PATTERN = re.compile(r"^h(?:\d+|[a-z][a-z0-9_]*)$")
INFRA_LIKE_PATTERN = re.compile(r"^(?:ce_|fw_).+|^(?:mpls_primary|mpls_backup|internet_zone)$")


def extract_live_namespaces(process_lines: Iterable[str]) -> set[str]:
    """Return unique Mininet node shell names from raw process command lines."""
    names: set[str] = set()
    for line in process_lines:
        names.update(MININET_NAME_PATTERN.findall(line))
    return names


def classify_live_namespaces(live_names: Iterable[str]) -> dict[str, set[str]]:
    """Classify only exact expected sets plus recognizable unexpected members."""
    live = set(live_names)
    users = {name for name in live if USER_NAME_PATTERN.fullmatch(name)}
    services = {
        name
        for name in live
        if name in EXPECTED_SERVICES
        or (
            SERVICE_LIKE_PATTERN.fullmatch(name)
            and name not in EXPECTED_USERS
            and name not in KNOWN_NON_SERVICE_NODES
            and name not in EXPECTED_INFRA_NAMESPACES
        )
    }
    infrastructure = {
        name
        for name in live
        if name in EXPECTED_INFRA_NAMESPACES or INFRA_LIKE_PATTERN.fullmatch(name)
    }
    enterprise = {name for name in live if name in EXPECTED_ENTERPRISE_ENDPOINTS}
    return {
        "live": live,
        "users": users,
        "services": services,
        "infrastructure": infrastructure,
        "enterprise": enterprise,
    }


def _words(values: Iterable[str]) -> str:
    return " ".join(sorted(set(values)))


def _report_set(label: str, expected: set[str] | frozenset[str], actual: set[str]) -> bool:
    missing = set(expected) - actual
    unexpected = actual - set(expected)
    print(f"EXPECTED_{label}_NAMES={_words(expected)}")
    print(f"ACTUAL_{label}_NAMES={_words(actual)}")
    print(f"{label}_NAMESPACE_COUNT={len(actual)}")
    print(f"MISSING_{label}_NAMES={_words(missing)}")
    print(f"UNEXPECTED_{label}_NAMES={_words(unexpected)}")
    if missing or unexpected:
        print(
            f"FAIL {label} namespace set mismatch: "
            f"missing=[{_words(missing)}] unexpected=[{_words(unexpected)}]"
        )
        return False
    print(f"PASS Dung {len(expected)} {label.lower()} namespace")
    return True


def render_report(process_lines: Iterable[str]) -> bool:
    inventory = classify_live_namespaces(extract_live_namespaces(process_lines))
    print(f"LIVE_NAMESPACE_NAMES={_words(inventory['live'])}")
    checks = (
        _report_set("USER", EXPECTED_USERS, inventory["users"]),
        _report_set("SERVICE", EXPECTED_SERVICES, inventory["services"]),
        _report_set(
            "INFRA",
            EXPECTED_INFRA_NAMESPACES,
            inventory["infrastructure"],
        ),
        _report_set(
            "ENTERPRISE",
            EXPECTED_ENTERPRISE_ENDPOINTS,
            inventory["enterprise"],
        ),
    )
    return all(checks)


def main() -> int:
    return 0 if render_report(sys.stdin) else 1


if __name__ == "__main__":
    raise SystemExit(main())
