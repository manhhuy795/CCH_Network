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
    EXPECTED_CONTROLLED_SWITCHES,
    EXPECTED_FIREWALL_NODES,
    EXPECTED_PHYSICAL_SITES,
    EXPECTED_SITES,
    build_host_inventory,
    load_network_model,
    validate_network_model,
)


EXPECTED_HQ_ISOLATION = {20: {30, 40}, 30: {20, 40}, 40: {20, 30}}
REQUIRED_TRANSIT_LINKS = {
    "core_hq_to_ce_hq": {"core_hq", "ce_hq"},
    "ce_hq_to_mpls_primary": {"ce_hq", "mpls_primary"},
    "mpls_primary_to_ce_telesale": {"mpls_primary", "ce_telesale"},
    "ce_hq_to_mpls_backup": {"ce_hq", "mpls_backup"},
    "mpls_backup_to_ce_telesale": {"mpls_backup", "ce_telesale"},
    "ce_telesale_to_dist_branch": {"ce_telesale", "dist_branch"},
    "core_hq_to_fw_hq": {"core_hq", "fw_hq"},
    "dist_branch_to_fw_branch": {"dist_branch", "fw_telesale"},
    "fw_hq_to_internet_zone": {"fw_hq", "internet_zone"},
    "fw_telesale_to_internet_zone": {"fw_telesale", "internet_zone"},
}
EXPECTED_SITE_MODEL_NODES = {
    "hq": {"access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2", "core_hq", "infra_access", "ce_hq", "fw_hq"},
    "branch_telesale": {"access_branch", "dist_branch", "ce_telesale", "fw_telesale"},
}
EXPECTED_PROVIDER_HANDOFFS = {
    "primary": {"provider_id": "isp_circuit_a", "handoff_id": "wan_handoff_primary", "state": "active", "color": "blue"},
    "backup": {"provider_id": "isp_circuit_b", "handoff_id": "wan_handoff_backup", "state": "standby", "color": "purple"},
}


def _network(value: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(value, strict=True)


def _model_node_ids(model: dict[str, Any]) -> set[str]:
    return set().union(model.get("host_groups", {}), model.get("services", {}), model.get("infrastructure_services", {}), model.get("switches", {}), model.get("infrastructure", {}))


def validate_all(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    model = load_network_model()
    errors.extend(validate_network_model(model))
    node_ids = _model_node_ids(model)

    vlans = config.get("vlans", [])
    vlan_ids = [int(item["id"]) for item in vlans]
    if len(vlan_ids) != len(set(vlan_ids)):
        errors.append("Duplicate VLAN IDs found")
    expected_vlans = {10, 20, 30, 40, 50, 60, 70, 90, 100, 110, 111, 120}
    if set(vlan_ids) != expected_vlans:
        errors.append(f"VLAN plan must be {sorted(expected_vlans)}, found {sorted(vlan_ids)}")
    for vlan in vlans:
        try:
            network = _network(str(vlan["subnet"]))
            gateway = ipaddress.ip_address(str(vlan["gateway"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"VLAN {vlan.get('id')} has invalid addressing: {exc}")
            continue
        if gateway not in network or gateway in {network.network_address, network.broadcast_address}:
            errors.append(f"VLAN {vlan['id']} gateway must be usable inside {network}")

    for source_vlan, denied in EXPECTED_HQ_ISOLATION.items():
        item = next((item for item in config.get("hq_project_isolation", []) if int(item.get("source_vlan", -1)) == source_vlan), None)
        if not item or not denied.issubset({int(value) for value in item.get("deny_destination_vlans", [])}):
            errors.append(f"VLAN {source_vlan} must deny project VLANs {sorted(denied)}")

    if set(config.get("sites", {})) != EXPECTED_SITES:
        errors.append(f"Automation sites must be {sorted(EXPECTED_SITES)}")
    if {name for name, item in config.get("sites", {}).items() if item.get("kind") == "physical"} != EXPECTED_PHYSICAL_SITES:
        errors.append(f"Automation physical sites must be {sorted(EXPECTED_PHYSICAL_SITES)}")

    devices: list[dict[str, Any]] = [device for site in config.get("sites", {}).values() for device in site.get("devices", [])]
    device_nodes = {str(device.get("model_node")) for device in devices}
    for site_name, expected_nodes in EXPECTED_SITE_MODEL_NODES.items():
        if {str(device.get("model_node")) for device in config.get("sites", {}).get(site_name, {}).get("devices", [])} != expected_nodes:
            errors.append(f"{site_name} managed nodes must be {sorted(expected_nodes)}")
    if len({device.get("name") for device in devices}) != len(devices):
        errors.append("Duplicate automation device names")
    if len({device.get("management_ip") for device in devices}) != len(devices):
        errors.append("Duplicate management IPs")
    if not device_nodes.issubset(node_ids):
        errors.append("Automation inventory references a missing source-of-truth node")
    expected_edge_inventory = {
        "fw_hq": {"design_role": "firewall_ha_logical_pair", "redundancy": "active_standby"},
        "fw_telesale": {"redundancy": "single_node_simulation"},
    }
    for model_node, expected in expected_edge_inventory.items():
        device = next((item for item in devices if item.get("model_node") == model_node), {})
        if device.get("outside_circuits") != ["primary", "backup"]:
            errors.append(f"Automation inventory {model_node} must declare primary and backup outside circuits")
        for key, value in expected.items():
            if device.get(key) != value:
                errors.append(f"Automation inventory {model_node} {key} must be {value!r}")

    routing = config.get("links", {})
    if set(routing) != set(REQUIRED_TRANSIT_LINKS):
        errors.append(f"Transit links must be exactly {sorted(REQUIRED_TRANSIT_LINKS)}")
    if config.get("transit_addressing", {}).get("prefix_length") != 30:
        errors.append("Transit addressing must use /30")
    transit_networks: list[tuple[str, ipaddress.IPv4Network]] = []
    transit_ips: set[str] = set()
    for name, expected_endpoints in REQUIRED_TRANSIT_LINKS.items():
        link = routing.get(name, {})
        try:
            network = _network(str(link["cidr"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"Transit link {name} has invalid CIDR: {exc}")
            continue
        if network.prefixlen != 30:
            errors.append(f"Transit link {name} must be /30")
        transit_networks.append((name, network))
        endpoints = []
        for key in ("endpoint_a", "endpoint_b"):
            endpoint = link.get(key, {})
            node, ip_text = str(endpoint.get("node", "")), str(endpoint.get("ip", ""))
            endpoints.append(node)
            if node not in node_ids:
                errors.append(f"Transit link {name} references missing node {node}")
            try:
                address = ipaddress.ip_address(ip_text)
            except ValueError:
                errors.append(f"Transit link {name} has invalid endpoint IP {ip_text}")
                continue
            if address not in network or address in {network.network_address, network.broadcast_address}:
                errors.append(f"Transit link {name} endpoint IP {ip_text} is not usable in {network}")
            if ip_text in transit_ips:
                errors.append(f"Duplicate transit IP {ip_text}")
            transit_ips.add(ip_text)
        if set(endpoints) != expected_endpoints:
            errors.append(f"Transit link {name} endpoints must be {sorted(expected_endpoints)}")
    for name, link in routing.items():
        for endpoint_key in ("endpoint_a", "endpoint_b"):
            node = str(link.get(endpoint_key, {}).get("node", ""))
            if node and node not in node_ids:
                errors.append(f"Routing link {name} references missing node {node}")
    for index, (left_name, left) in enumerate(transit_networks):
        for right_name, right in transit_networks[index + 1:]:
            if left.overlaps(right):
                errors.append(f"Transit CIDR overlap: {left_name} and {right_name}")

    declared_networks: list[tuple[str, ipaddress.IPv4Network]] = []
    for vlan in config.get("vlans", []):
        try:
            declared_networks.append((f"vlan_{vlan['id']}", _network(str(vlan["subnet"]))))
        except (KeyError, ValueError):
            continue
    for category in ("host_groups", "services", "infrastructure_services"):
        for name, item in model.get(category, {}).items():
            if item.get("subnet"):
                try:
                    declared_networks.append((f"{category}.{name}", ipaddress.ip_network(str(item["subnet"]), strict=False)))
                except ValueError:
                    continue
    service_zone_cidr = config.get("service_zone", {}).get("cidr")
    if service_zone_cidr:
        declared_networks.append(("service_zone", _network(str(service_zone_cidr))))
    for transit_name, transit in transit_networks:
        for declared_name, declared in declared_networks:
            if transit.overlaps(declared):
                errors.append(f"Transit CIDR overlaps declared subnet: {transit_name} and {declared_name}")

    provider_handoffs = config.get("provider_handoff_paths", {})
    if set(provider_handoffs) != set(EXPECTED_PROVIDER_HANDOFFS):
        errors.append(f"Provider handoff paths must be {sorted(EXPECTED_PROVIDER_HANDOFFS)}")
    for name, expected in EXPECTED_PROVIDER_HANDOFFS.items():
        item = provider_handoffs.get(name, {})
        for key, value in expected.items():
            if item.get(key) != value:
                errors.append(f"Provider handoff {name} {key} must be {value!r}")
        if item.get("representation") != "design_only" or item.get("runtime_node") is not None or item.get("runtime_state") != "design_only" or item.get("controller_managed") is not False:
            errors.append(f"Provider handoff {name} must be explicitly design-only")
        handoff_sites = item.get("site_firewalls", {})
        if set(handoff_sites) != set(EXPECTED_PHYSICAL_SITES):
            errors.append(f"Provider handoff {name} must terminate at HQ and Branch Telesale")
        for site, firewall in (("hq", "fw_hq"), ("branch_telesale", "fw_telesale")):
            endpoint = handoff_sites.get(site, {})
            if endpoint.get("firewall") != firewall:
                errors.append(f"Provider handoff {name} {site} firewall must be {firewall}")
            expected_runtime_link = {
                "hq": "fw_hq_to_internet_zone",
                "branch_telesale": "fw_telesale_to_internet_zone",
            }[site]
            if endpoint.get("runtime_link") != expected_runtime_link or endpoint.get("runtime_link") not in routing:
                errors.append(f"Provider handoff {name} {site} must reference {expected_runtime_link}")

    firewall_sites = config.get("firewall_policy", {}).get("sites", {})
    expected_ownership = {
        "hq": ("fw_hq", "core_hq", {"172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.60.0/24", "172.16.70.0/24", "172.16.90.0/24", "172.16.100.0/24", "172.16.110.0/24", "172.16.120.0/24"}),
        "branch_telesale": ("fw_telesale", "dist_branch", {"172.16.50.0/24", "172.16.111.0/24"}),
    }
    if set(firewall_sites) != set(expected_ownership):
        errors.append("Firewall policy sites must be HQ and Branch Telesale")
    for site, (firewall, inside, subnets) in expected_ownership.items():
        item = firewall_sites.get(site, {})
        if (item.get("firewall_name"), item.get("inside_node"), set(item.get("owned_subnets", []))) != (firewall, inside, subnets):
            errors.append(f"Firewall ownership is incorrect for {site}")
        if item.get("outside_node") != "internet_zone":
            errors.append(f"Firewall {site} must use internet_zone as outside node")

    expected_runtime_interfaces = {
        "hq": {"inside": "fw_hq-eth0", "outside": "fw_hq-eth1"},
        "branch_telesale": {"inside": "fw_tel-eth0", "outside": "fw_tel-eth1"},
    }
    for site, expected_interfaces in expected_runtime_interfaces.items():
        if firewall_sites.get(site, {}).get("runtime_interfaces") != expected_interfaces:
            errors.append(f"Firewall policy {site} has incorrect runtime interfaces")

    expected_firewall_design = {
        "hq": ("active_standby", ["fw_hq_primary", "fw_hq_backup"]),
        "branch_telesale": ("single_firewall_simulation", None),
    }
    for site, (redundancy, members) in expected_firewall_design.items():
        item = firewall_sites.get(site, {})
        if item.get("design_redundancy") != redundancy:
            errors.append(f"Firewall policy {site} design_redundancy must be {redundancy}")
        if members is not None and item.get("design_members") != members:
            errors.append(f"Firewall policy {site} design_members must be {members}")
        if item.get("outside_circuits") != ["primary", "backup"]:
            errors.append(f"Firewall policy {site} must declare primary and backup outside circuits")

    defaults = config.get("firewall_policy", {}).get("runtime_defaults", {})
    expected_defaults = {
        "engine": "nftables",
        "family": "inet",
        "table_name": "cch_filter",
        "input_policy": "drop",
        "forward_policy": "drop",
        "output_policy": "accept",
        "chain_priority": 0,
        "allow_established_related": True,
        "drop_invalid": True,
        "counter_enabled": True,
    }
    for key, expected in expected_defaults.items():
        if defaults.get(key) != expected:
            errors.append(f"firewall runtime default {key} must be {expected!r}")
    nat = defaults.get("nat", {})
    if nat.get("enabled") is not False or nat.get("mode") != "routed_lab":
        errors.append("NAT must remain disabled in routed_lab mode until runtime proof")
    if nat.get("runtime_verification_required") is not True:
        errors.append("NAT decision must require Ubuntu runtime verification")

    firewall_link_roles = {
        "fw_hq": ("core_hq", "fw_hq_to_internet_zone"),
        "fw_telesale": ("dist_branch", "fw_telesale_to_internet_zone"),
    }
    for firewall, (inside_node, outside_link_name) in firewall_link_roles.items():
        inside_links = [
            name for name, link in routing.items()
            if firewall in {link.get("endpoint_a", {}).get("node"), link.get("endpoint_b", {}).get("node")}
            and link.get("role") == "firewall_inside"
            and inside_node in {link.get("endpoint_a", {}).get("node"), link.get("endpoint_b", {}).get("node")}
        ]
        outside_links = [
            name for name, link in routing.items()
            if name == outside_link_name
            and firewall in {link.get("endpoint_a", {}).get("node"), link.get("endpoint_b", {}).get("node")}
            and link.get("role") == "firewall_outside"
        ]
        if len(inside_links) != 1 or len(outside_links) != 1:
            errors.append(f"{firewall} must have one firewall_inside and one firewall_outside link")

    for host in build_host_inventory(model).values():
        if host["ip"] in transit_ips:
            errors.append(f"Endpoint {host['name']} overlaps a transit endpoint IP")
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
