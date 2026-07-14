from __future__ import annotations

import ipaddress
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import load_vars
from scripts.network_model import load_network_model, validate_network_model


EXPECTED_HQ_ISOLATION = {
    20: {30, 40},
    30: {20, 40},
    40: {20, 30},
}


def _network(prefix: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(prefix, strict=True)


def _all_route_entries(routes: dict[str, Any]) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    for device_name, route_data in routes.items():
        default_route = route_data.get("default_route")
        if default_route:
            entries.append((device_name, "0.0.0.0/0", str(default_route["next_hop"])))
        for key in ("intersite_routes", "internal_routes", "mpls_routes"):
            for route in route_data.get(key, []):
                entries.append((device_name, str(route["prefix"]), str(route["next_hop"])))
    return entries


def validate_all(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_network_model(load_network_model()))

    vlan_ids = [int(vlan["id"]) for vlan in config.get("vlans", [])]
    duplicates = sorted({vlan_id for vlan_id in vlan_ids if vlan_ids.count(vlan_id) > 1})
    if duplicates:
        errors.append(f"Duplicate VLAN IDs found: {duplicates}")

    vlan_by_id = {int(vlan["id"]): vlan for vlan in config.get("vlans", [])}
    for vlan in config.get("vlans", []):
        try:
            network = _network(str(vlan["subnet"]))
        except ValueError as exc:
            errors.append(f"VLAN {vlan.get('id')} has invalid subnet {vlan.get('subnet')}: {exc}")
            continue
        try:
            gateway = ipaddress.ip_address(str(vlan["gateway"]))
        except ValueError as exc:
            errors.append(f"VLAN {vlan.get('id')} has invalid gateway {vlan.get('gateway')}: {exc}")
            continue
        if gateway not in network:
            errors.append(f"VLAN {vlan['id']} gateway {gateway} is outside subnet {network}")
        if gateway in {network.network_address, network.broadcast_address}:
            errors.append(f"VLAN {vlan['id']} gateway {gateway} cannot be network/broadcast address")

    for policy in config.get("hq_project_isolation", []):
        source_vlan = int(policy["source_vlan"])
        expected_denies = EXPECTED_HQ_ISOLATION.get(source_vlan)
        actual_denies = {int(vlan) for vlan in policy.get("deny_destination_vlans", [])}
        if expected_denies and not expected_denies.issubset(actual_denies):
            errors.append(
                f"{policy['name']} for VLAN {source_vlan} must deny VLANs {sorted(expected_denies)}"
            )
        for destination in actual_denies:
            if destination not in vlan_by_id:
                errors.append(f"{policy['name']} references missing destination VLAN {destination}")

    branch_sources = {int(policy["source_vlan"]) for policy in config.get("branch_policies", [])}
    if branch_sources != {50, 60}:
        errors.append("Branch VLAN 50 and VLAN 60 must each have an explicit policy")

    routes = config.get("routes", {})
    links = config.get("links", {})
    hq_core_default = routes.get("hq-core-l3", {}).get("default_route", {}).get("next_hop")
    if hq_core_default != links.get("hq", {}).get("core_to_firewall", {}).get("firewall_inside_ip", "").split("/")[0]:
        errors.append("HQ core default route must point to HQ firewall inside IP")

    branch_default = routes.get("br-dist-l3", {}).get("default_route", {}).get("next_hop")
    if branch_default != links.get("branch", {}).get("distribution_to_firewall", {}).get("firewall_inside_ip", "").split("/")[0]:
        errors.append("Branch distribution default route must point to Branch firewall inside IP")

    hq_ce_next_hops = {route["next_hop"] for route in routes.get("hq-ce-router", {}).get("mpls_routes", [])}
    if hq_ce_next_hops != {links.get("hq", {}).get("ce_to_pe", {}).get("pe_ip")}:
        errors.append("HQ CE MPLS routes must point only to HQ ISP PE IP")

    branch_ce_next_hops = {route["next_hop"] for route in routes.get("br-ce-router", {}).get("mpls_routes", [])}
    if branch_ce_next_hops != {links.get("branch", {}).get("ce_to_pe", {}).get("pe_ip")}:
        errors.append("Branch CE MPLS routes must point only to Branch ISP PE IP")

    ce_ips = set()
    for ce_data in config.get("ce_router_ips", {}).values():
        ce_ips.add(str(ce_data.get("lan_ip")))
        ce_ips.add(str(ce_data.get("wan_ip")))
    provider_pe_ips = {
        links.get("hq", {}).get("ce_to_pe", {}).get("pe_ip"),
        links.get("branch", {}).get("ce_to_pe", {}).get("pe_ip"),
    }
    for device_name, prefix, next_hop in _all_route_entries(routes):
        try:
            ipaddress.ip_network(prefix, strict=False)
            ipaddress.ip_address(next_hop)
        except ValueError as exc:
            errors.append(f"{device_name} route {prefix} via {next_hop} is invalid: {exc}")
        if device_name.endswith("ce-router") and next_hop in ce_ips and next_hop not in provider_pe_ips:
            route_is_internal = prefix in {vlan["subnet"] for vlan in config.get("vlans", [])}
            if not route_is_internal:
                errors.append(f"{device_name} has forbidden CE-to-CE-style next-hop {next_hop} for {prefix}")
        if device_name.endswith("ce-router"):
            remote_ce_ips = ce_ips - {
                config.get("ce_router_ips", {}).get(device_name, {}).get("lan_ip"),
                config.get("ce_router_ips", {}).get(device_name, {}).get("wan_ip"),
            }
            if next_hop in remote_ce_ips:
                errors.append(f"{device_name} must not route directly to remote CE IP {next_hop}")

    return errors


def main() -> int:
    errors = validate_all(load_vars())
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
