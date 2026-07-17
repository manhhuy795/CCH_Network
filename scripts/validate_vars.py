from __future__ import annotations

import ipaddress
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import load_vars
from scripts.network_model import (
    EXPECTED_CE_NODES,
    EXPECTED_FIREWALL_NODES,
    EXPECTED_PHYSICAL_SITES,
    EXPECTED_SITES,
    FORBIDDEN_TOPOLOGY_NODES,
    build_host_inventory,
    load_network_model,
    validate_network_model,
)


EXPECTED_HQ_ISOLATION = {
    20: {30, 40},
    30: {20, 40},
    40: {20, 30},
}
REQUIRED_TRANSIT_LINKS = {
    "core_hq_to_ce_hq": {"core_hq", "ce_hq"},
    "ce_hq_to_mpls_cloud": {"ce_hq", "mpls_cloud"},
    "mpls_cloud_to_ce_telesale": {"mpls_cloud", "ce_telesale"},
    "ce_telesale_to_dist_telesale": {"ce_telesale", "dist_telesale"},
    "core_hq_to_fw_hq": {"core_hq", "fw_hq"},
    "dist_telesale_to_fw_telesale": {"dist_telesale", "fw_telesale"},
    "fw_hq_to_internet_zone": {"fw_hq", "internet_zone"},
    "fw_telesale_to_internet_zone": {"fw_telesale", "internet_zone"},
}
EXPECTED_SITE_MODEL_NODES = {
    "hq": {
        "access_hq_a", "access_hq_b", "access_hq_c", "access_backoffice",
        "voice_access", "access_hq_it", "core_hq", "ce_hq", "fw_hq",
    },
    "branch_telesale": {"access_telesale", "dist_telesale", "ce_telesale", "fw_telesale"},
}


def _network(prefix: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(prefix, strict=True)


def _all_route_entries(routes: dict[str, Any]) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    for device_name, route_data in routes.items():
        default_route = route_data.get("default_route")
        if default_route:
            entries.append((device_name, "0.0.0.0/0", str(default_route["next_hop"])))
        for key in ("intersite_routes", "internal_routes", "mpls_routes", "service_routes"):
            for route in route_data.get(key, []):
                entries.append((device_name, str(route["prefix"]), str(route["next_hop"])))
    return entries


def _model_node_ids(model: dict[str, Any]) -> set[str]:
    return set().union(
        model.get("host_groups", {}),
        model.get("services", {}),
        model.get("switches", {}),
        model.get("infrastructure", {}),
    )


def validate_all(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    model = load_network_model()
    errors.extend(validate_network_model(model))

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

    intersite_sources = {int(policy["source_vlan"]) for policy in config.get("branch_policies", [])}
    if intersite_sources != {50, 60}:
        errors.append("Telesale VLAN 50 and HQ BackOffice VLAN 60 must each have an explicit intersite policy")

    node_ids = _model_node_ids(model)
    sites = config.get("sites", {})
    if set(sites) != EXPECTED_SITES:
        errors.append(f"Automation sites must be exactly {sorted(EXPECTED_SITES)}, found {sorted(sites)}")
    physical_sites = {name for name, site in sites.items() if site.get("kind") == "physical"}
    if physical_sites != EXPECTED_PHYSICAL_SITES:
        errors.append(
            f"Automation physical sites must be exactly {sorted(EXPECTED_PHYSICAL_SITES)}, "
            f"found {sorted(physical_sites)}"
        )

    expected_vlan_sites = {10: "hq", 20: "hq", 30: "hq", 40: "hq", 50: "branch_telesale", 60: "hq", 70: "hq", 90: "hq"}
    for vlan_id, expected_site in expected_vlan_sites.items():
        actual_site = vlan_by_id.get(vlan_id, {}).get("site")
        if actual_site != expected_site:
            errors.append(f"VLAN {vlan_id} site must be {expected_site}, found {actual_site}")

    device_names: list[str] = []
    management_ips: list[str] = []
    model_nodes: list[str] = []
    for site_name, site in sites.items():
        for device in site.get("devices", []):
            device_names.append(str(device.get("name")))
            management_ips.append(str(device.get("management_ip")))
            model_node = str(device.get("model_node", ""))
            model_nodes.append(model_node)
            if device.get("site") != site_name:
                errors.append(f"Device {device.get('name')} site must be {site_name}")
            if model_node not in node_ids:
                errors.append(f"Device {device.get('name')} references missing model_node {model_node}")
    for label, values in (("device names", device_names), ("management IPs", management_ips), ("model_node mappings", model_nodes)):
        duplicates = sorted({value for value in values if value and values.count(value) > 1})
        if duplicates:
            errors.append(f"Duplicate {label} found: {duplicates}")
    for site_name, expected_nodes in EXPECTED_SITE_MODEL_NODES.items():
        actual_nodes = {str(device.get("model_node")) for device in sites.get(site_name, {}).get("devices", [])}
        if actual_nodes != expected_nodes:
            errors.append(f"{site_name} managed nodes must be {sorted(expected_nodes)}, found {sorted(actual_nodes)}")

    interfaces = config.get("interfaces", {})
    for site in sites.values():
        for device in site.get("devices", []):
            if device.get("role") != "access_switch":
                continue
            device_name = str(device.get("name"))
            mapping = interfaces.get(device_name, {})
            access_ports = mapping.get("access_ports", [])
            uplink = mapping.get("uplink", {})
            expected_access_vlans = {int(vlan) for vlan in device.get("access_vlans", [])}
            mapped_access_vlans = {int(port["vlan"]) for port in access_ports if "vlan" in port}
            uplink_vlans = {int(vlan) for vlan in uplink.get("allowed_vlans", [])}
            if not access_ports:
                errors.append(f"Access switch {device_name} must define at least one access_ports mapping")
            if mapped_access_vlans != expected_access_vlans:
                errors.append(
                    f"Access switch {device_name} access port VLANs must be {sorted(expected_access_vlans)}, "
                    f"found {sorted(mapped_access_vlans)}"
                )
            if not uplink.get("name"):
                errors.append(f"Access switch {device_name} must define an uplink interface")
            if not expected_access_vlans.issubset(uplink_vlans):
                errors.append(
                    f"Access switch {device_name} uplink must carry VLANs {sorted(expected_access_vlans)}"
                )

    links = config.get("links", {})
    if set(links) != set(REQUIRED_TRANSIT_LINKS):
        errors.append(
            f"Transit links must be exactly {sorted(REQUIRED_TRANSIT_LINKS)}, found {sorted(links)}"
        )
    if int(config.get("transit_addressing", {}).get("prefix_length", 0)) != 30:
        errors.append("Transit addressing must declare /30 for Mininet/Linux compatibility")
    if not str(config.get("transit_addressing", {}).get("rationale", "")).strip():
        errors.append("Transit addressing must document the /30 rationale")

    transit_networks: dict[str, ipaddress.IPv4Network] = {}
    transit_ips: dict[str, str] = {}
    adjacent_next_hops: dict[str, set[str]] = {}
    firewall_link_roles = {firewall: set() for firewall in EXPECTED_FIREWALL_NODES}
    for link_name, expected_endpoints in REQUIRED_TRANSIT_LINKS.items():
        link = links.get(link_name, {})
        try:
            network = _network(str(link["cidr"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"Transit link {link_name} has invalid CIDR: {exc}")
            continue
        transit_networks[link_name] = network
        if network.prefixlen != 30:
            errors.append(f"Transit link {link_name} must use /30, found {network}")
        endpoints: list[tuple[str, str]] = []
        for endpoint_key in ("endpoint_a", "endpoint_b"):
            endpoint = link.get(endpoint_key, {})
            node = str(endpoint.get("node", ""))
            ip_text = str(endpoint.get("ip", ""))
            endpoints.append((node, ip_text))
            if node not in node_ids:
                errors.append(f"Transit link {link_name} references missing endpoint {node}")
            try:
                address = ipaddress.ip_address(ip_text)
            except ValueError as exc:
                errors.append(f"Transit link {link_name} endpoint {node} has invalid IP {ip_text}: {exc}")
                continue
            if address not in network or address in {network.network_address, network.broadcast_address}:
                errors.append(f"Transit link {link_name} endpoint {node} IP {address} is not usable in {network}")
            if ip_text in transit_ips:
                errors.append(f"Duplicate transit endpoint IP {ip_text} on {transit_ips[ip_text]} and {link_name}")
            transit_ips[ip_text] = link_name
        if {node for node, _ip in endpoints} != expected_endpoints:
            errors.append(
                f"Transit link {link_name} endpoints must be {sorted(expected_endpoints)}, "
                f"found {sorted(node for node, _ip in endpoints)}"
            )
        if len(endpoints) == 2:
            (node_a, ip_a), (node_b, ip_b) = endpoints
            adjacent_next_hops.setdefault(node_a, set()).add(ip_b)
            adjacent_next_hops.setdefault(node_b, set()).add(ip_a)
        for firewall in expected_endpoints & EXPECTED_FIREWALL_NODES:
            firewall_link_roles[firewall].add(str(link.get("role")))

    transit_items = list(transit_networks.items())
    for index, (left_name, left_network) in enumerate(transit_items):
        for right_name, right_network in transit_items[index + 1:]:
            if left_network.overlaps(right_network):
                errors.append(f"Transit CIDR overlap: {left_name} {left_network} and {right_name} {right_network}")
    for firewall, roles in firewall_link_roles.items():
        if roles != {"firewall_inside", "firewall_outside"}:
            errors.append(f"{firewall} must have one firewall_inside and one firewall_outside transit link")

    allocated_networks: list[tuple[str, ipaddress.IPv4Network]] = []
    for vlan in config.get("vlans", []):
        try:
            allocated_networks.append((f"VLAN {vlan['id']}", _network(str(vlan["subnet"]))))
        except ValueError:
            pass
    for service_name, service in model.get("services", {}).items():
        if service_name == "h90":
            continue
        try:
            allocated_networks.append((f"service {service_name}", _network(str(service["subnet"]))))
        except (KeyError, ValueError):
            pass
    try:
        allocated_networks.append(("service transit zone", _network(str(config["service_zone"]["cidr"]))))
    except (KeyError, ValueError) as exc:
        errors.append(f"Service transit zone has invalid CIDR: {exc}")
    allocated_networks.extend((f"transit {name}", network) for name, network in transit_networks.items())
    for index, (left_name, left_network) in enumerate(allocated_networks):
        for right_name, right_network in allocated_networks[index + 1:]:
            if left_network.overlaps(right_network):
                errors.append(f"Subnet overlap: {left_name} {left_network} and {right_name} {right_network}")

    address_owners: dict[str, str] = {}
    def record_address(value: Any, owner: str) -> None:
        address = str(value or "")
        try:
            ipaddress.ip_address(address)
        except ValueError:
            errors.append(f"{owner} has invalid IP address {address!r}")
            return
        if address in address_owners:
            errors.append(f"Duplicate IP address {address}: {address_owners[address]} and {owner}")
        address_owners[address] = owner

    for host in build_host_inventory(model).values():
        record_address(host["ip"], f"endpoint {host['name']}")
    for group_name, group in model.get("host_groups", {}).items():
        record_address(group.get("gateway"), f"gateway {group_name}")
    for site_name, site in sites.items():
        for device in site.get("devices", []):
            record_address(device.get("management_ip"), f"management {device.get('name')}")
    for service_name, service in model.get("services", {}).items():
        if service.get("interface_ip"):
            record_address(service["interface_ip"], f"service interface {service_name}")
    record_address(config.get("service_zone", {}).get("gateway_ip"), "service zone gateway")
    for ip_text, link_name in transit_ips.items():
        record_address(ip_text, f"transit {link_name}")

    firewall_sites = config.get("firewall_policy", {}).get("sites", {})
    expected_firewall_sites = {"hq", "branch_telesale"}
    expected_firewall_ownership = {
        "hq": ("fw_hq", "core_hq", {"172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.60.0/24", "172.16.70.0/24"}),
        "branch_telesale": ("fw_telesale", "dist_telesale", {"172.16.50.0/24"}),
    }
    if set(firewall_sites) != expected_firewall_sites:
        errors.append(f"Firewall policy sites must be {sorted(expected_firewall_sites)}")
    for site_name, policy in firewall_sites.items():
        firewall_name = str(policy.get("firewall_name", ""))
        if firewall_name not in EXPECTED_FIREWALL_NODES:
            errors.append(f"Firewall policy {site_name} references invalid firewall {firewall_name}")
        if policy.get("site") != site_name:
            errors.append(f"Firewall policy {site_name} has mismatched site {policy.get('site')}")
        if policy.get("inside_node") == policy.get("outside_node"):
            errors.append(f"Firewall policy {site_name} inside and outside nodes must differ")
        expected_firewall, expected_inside, expected_subnets = expected_firewall_ownership.get(
            site_name, ("", "", set())
        )
        if firewall_name != expected_firewall or policy.get("inside_node") != expected_inside:
            errors.append(f"Firewall policy {site_name} has incorrect firewall/inside ownership")
        if policy.get("outside_node") != "internet_zone":
            errors.append(f"Firewall policy {site_name} outside node must be internet_zone")
        if set(policy.get("owned_subnets", [])) != expected_subnets:
            errors.append(f"Firewall policy {site_name} owns incorrect subnets")

    routes = config.get("routes", {})
    legacy_route_nodes = sorted(set(routes) & FORBIDDEN_TOPOLOGY_NODES)
    if legacy_route_nodes:
        errors.append(f"Routes still reference legacy or retired topology nodes: {legacy_route_nodes}")
    for device_name in routes:
        if device_name not in node_ids:
            errors.append(f"Routes reference missing topology node {device_name}")

    service_zone = config.get("service_zone", {})
    service_network = ipaddress.ip_network(str(service_zone.get("cidr", "0.0.0.0/32")), strict=True)
    expected_service_routes = {}
    for service_name in service_zone.get("service_nodes", []):
        service = model.get("services", {}).get(service_name, {})
        interface_ip = str(service.get("interface_ip", ""))
        try:
            interface_address = ipaddress.ip_address(interface_ip)
        except ValueError:
            errors.append(f"Service {service_name} has invalid interface IP {interface_ip!r}")
            continue
        if interface_address not in service_network:
            errors.append(f"Service {service_name} interface IP {interface_ip} is outside {service_network}")
        adjacent_next_hops.setdefault("internet_zone", set()).add(interface_ip)
        expected_service_routes[f"{service.get('ip')}/32"] = interface_ip
    actual_service_routes = {
        str(route.get("prefix")): str(route.get("next_hop"))
        for route in routes.get("internet_zone", {}).get("service_routes", [])
    }
    if actual_service_routes != expected_service_routes:
        errors.append(
            f"internet_zone service routes must be {expected_service_routes}, found {actual_service_routes}"
        )
    if service_zone.get("addressing_model") != "interface_plus_service_vip":
        errors.append("service_zone must declare interface_plus_service_vip addressing")

    for device_name, prefix, next_hop in _all_route_entries(routes):
        try:
            ipaddress.ip_network(prefix, strict=False)
            ipaddress.ip_address(next_hop)
        except ValueError as exc:
            errors.append(f"{device_name} route {prefix} via {next_hop} is invalid: {exc}")
        if next_hop not in adjacent_next_hops.get(device_name, set()):
            errors.append(f"{device_name} route {prefix} next-hop {next_hop} is not directly adjacent")

    ce_router_ips = config.get("ce_router_ips", {})
    if set(ce_router_ips) != EXPECTED_CE_NODES:
        errors.append(f"ce_router_ips must define exactly {sorted(EXPECTED_CE_NODES)}")
    ce_ips = {
        str(ip_value)
        for ce_data in ce_router_ips.values()
        for ip_value in (ce_data.get("lan_ip"), ce_data.get("wan_ip"))
    }
    for ce_name in EXPECTED_CE_NODES:
        remote_ce_ips = ce_ips - {
            str(ce_router_ips.get(ce_name, {}).get("lan_ip")),
            str(ce_router_ips.get(ce_name, {}).get("wan_ip")),
        }
        for _device_name, prefix, next_hop in [entry for entry in _all_route_entries(routes) if entry[0] == ce_name]:
            if next_hop in remote_ce_ips:
                errors.append(f"{ce_name} must not route directly to remote CE IP {next_hop} for {prefix}")
        provider_next_hop = str(routes.get(ce_name, {}).get("provider_next_hop", ""))
        if provider_next_hop not in adjacent_next_hops.get(ce_name, set()):
            errors.append(f"{ce_name} provider_next_hop {provider_next_hop} is not its MPLS peer")

    expected_defaults = {
        "core_hq": "10.10.254.2",
        "dist_telesale": "10.20.254.2",
        "fw_hq": "10.255.10.2",
        "fw_telesale": "10.255.10.6",
    }
    for node_name, expected_next_hop in expected_defaults.items():
        actual = str(routes.get(node_name, {}).get("default_route", {}).get("next_hop", ""))
        if actual != expected_next_hop:
            errors.append(f"{node_name} default route must use {expected_next_hop}, found {actual}")

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
