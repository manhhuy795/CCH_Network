from __future__ import annotations

import ipaddress
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import all_devices, load_vars
from scripts.network_model import (
    EXPECTED_CE_NODES,
    EXPECTED_CONTROLLED_SWITCHES,
    EXPECTED_FIREWALL_NODES,
    EXPECTED_PHYSICAL_SITES,
    EXPECTED_SITES,
    load_network_model,
    validate_network_model,
)


EXPECTED_VLANS = {10, 50, 93, 100, 101, 103, 104, 110, 120, 140}
EXPECTED_PROJECT_ISOLATION = {
    101: {93, 103, 104},
    93: {101, 103, 104},
    103: {93, 101, 104},
    104: {93, 101, 103},
}
EXPECTED_ROUTING_LINKS = {
    "hq_l3_to_fw_hq": {"hq_l3_gateway", "fw_hq"},
    "fw_hq_to_ipsec": {"fw_hq", "ipsec_l3"},
    "ipsec_to_fw_branch": {"ipsec_l3", "fw_telesale"},
    "branch_l3_to_fw_branch": {"telesale_l3_gateway", "fw_telesale"},
    "fw_hq_to_internet_zone": {"fw_hq", "internet_zone"},
    "fw_branch_to_internet_zone": {"fw_telesale", "internet_zone"},
}
EXPECTED_AUTOMATION_NODES = {
    "hq": {"access_floor1", "access_floor2", "core_hq", "infra_access", "ce_hq1", "ce_hq2", "fw_hq"},
    "branch": {"access_branch", "dist_branch", "ce_branch1", "ce_branch2", "fw_telesale"},
}
RUNTIME_ONLY_ROUTER_NODES = {"hq_l3_gateway", "telesale_l3_gateway"}
PROJECT_SERVICE_HOSTS = {"10.10.100.10", "10.10.100.11", "10.10.100.12", "10.10.100.13", "10.10.100.16"}
INTERNAL_PREFIXES = {"10.10.0.0/16", "10.20.0.0/16"}


def _network(value: str) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(value, strict=True)


def _all_model_nodes(model: dict[str, Any]) -> set[str]:
    nodes: set[str] = set()
    for category in ("host_groups", "services", "infrastructure_services", "switches", "infrastructure"):
        nodes.update(str(name) for name in model.get(category, {}))
    return nodes


def _validate_vlans(config: dict[str, Any], errors: list[str]) -> None:
    vlans = list(config.get("vlans", []))
    ids = [int(item["id"]) for item in vlans]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate VLAN IDs found")
    if set(ids) != EXPECTED_VLANS:
        errors.append(f"VLAN plan must be {sorted(EXPECTED_VLANS)}, found {sorted(ids)}")
    networks: list[tuple[int, ipaddress.IPv4Network]] = []
    for vlan in vlans:
        try:
            network = _network(str(vlan["subnet"]))
            gateway = ipaddress.ip_address(str(vlan["gateway"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"VLAN {vlan.get('id')} has invalid addressing: {exc}")
            continue
        if gateway not in network or gateway in {network.network_address, network.broadcast_address}:
            errors.append(f"VLAN {vlan['id']} gateway is not usable inside {network}")
        networks.append((int(vlan["id"]), network))
    for index, (left_id, left) in enumerate(networks):
        for right_id, right in networks[index + 1:]:
            if left.overlaps(right):
                errors.append(f"VLAN subnet overlap: {left_id} and {right_id}")

    vlan93 = next((item for item in vlans if int(item["id"]) == 93), {})
    if vlan93.get("subnet") != "10.10.93.0/24" or vlan93.get("gateway") != "10.10.93.1":
        errors.append("VLAN 93 must use 10.10.93.0/24 with gateway 10.10.93.1")
    if vlan93.get("gateway_site") != "hq" or vlan93.get("scope") != "stretched":
        errors.append("VLAN 93 must be stretched with its gateway owned by HQ")


def _validate_sites_and_devices(config: dict[str, Any], model: dict[str, Any], errors: list[str]) -> None:
    sites = config.get("sites", {})
    if set(sites) != EXPECTED_SITES:
        errors.append(f"Automation sites must be {sorted(EXPECTED_SITES)}")
    physical = {name for name, item in sites.items() if item.get("kind") == "physical"}
    if physical != EXPECTED_PHYSICAL_SITES:
        errors.append(f"Physical sites must be {sorted(EXPECTED_PHYSICAL_SITES)}")

    devices = all_devices(config)
    names = [str(item.get("name")) for item in devices]
    management_ips = [str(item.get("management_ip")) for item in devices if item.get("management_ip")]
    if len(names) != len(set(names)):
        errors.append("Duplicate automation device names")
    if len(management_ips) != len(set(management_ips)):
        errors.append("Duplicate management IPs")

    model_nodes = _all_model_nodes(model)
    for site_name, expected_nodes in EXPECTED_AUTOMATION_NODES.items():
        observed = {str(item.get("model_node")) for item in sites.get(site_name, {}).get("devices", [])}
        if observed != expected_nodes:
            errors.append(f"{site_name} automation nodes must be {sorted(expected_nodes)}, found {sorted(observed)}")
    for device in devices:
        model_node = str(device.get("model_node", ""))
        if model_node not in model_nodes:
            errors.append(f"Automation device {device.get('name')} references missing model node {model_node}")
        template = Path(__file__).resolve().parents[1] / "templates" / str(device.get("template", ""))
        if not template.is_file():
            errors.append(f"Automation device {device.get('name')} references missing template {device.get('template')}")

    branch_core = next((item for item in devices if item.get("model_node") == "dist_branch"), {})
    if 93 not in set(int(value) for value in branch_core.get("no_svi_vlans", [])):
        errors.append("Branch collapsed core must explicitly suppress SVI VLAN 93")
    if 93 in set(int(value) for value in branch_core.get("svi_vlans", [])):
        errors.append("Branch collapsed core must not create SVI VLAN 93")

    ce_nodes = {str(item.get("model_node")) for item in devices if item.get("role") == "ce_l2vpn_edge"}
    if ce_nodes != EXPECTED_CE_NODES:
        errors.append(f"Automation must contain four CE L2VPN edge devices: {sorted(EXPECTED_CE_NODES)}")
    firewall_nodes = {str(item.get("model_node")) for item in devices if item.get("role") == "firewall"}
    if firewall_nodes != EXPECTED_FIREWALL_NODES:
        errors.append(f"Automation firewall nodes must be {sorted(EXPECTED_FIREWALL_NODES)}")


def _validate_routing(config: dict[str, Any], model: dict[str, Any], errors: list[str]) -> None:
    links = config.get("links", {})
    if set(links) != set(EXPECTED_ROUTING_LINKS):
        errors.append(f"Routed links must be exactly {sorted(EXPECTED_ROUTING_LINKS)}")
    if int(config.get("transit_addressing", {}).get("prefix_length", 0)) != 30:
        errors.append("Routed transit addressing must use /30")

    allowed_nodes = _all_model_nodes(model) | RUNTIME_ONLY_ROUTER_NODES
    transit_networks: list[tuple[str, ipaddress.IPv4Network]] = []
    transit_ips: set[str] = set()
    for name, expected_nodes in EXPECTED_ROUTING_LINKS.items():
        link = links.get(name, {})
        try:
            network = _network(str(link["cidr"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"Routing link {name} has invalid CIDR: {exc}")
            continue
        if network.prefixlen != 30:
            errors.append(f"Routing link {name} must use /30")
        transit_networks.append((name, network))
        observed_nodes: set[str] = set()
        for endpoint_key in ("endpoint_a", "endpoint_b"):
            endpoint = link.get(endpoint_key, {})
            node = str(endpoint.get("node", ""))
            ip_text = str(endpoint.get("ip", ""))
            observed_nodes.add(node)
            if node not in allowed_nodes:
                errors.append(f"Routing link {name} references missing node {node}")
            try:
                address = ipaddress.ip_address(ip_text)
            except ValueError:
                errors.append(f"Routing link {name} has invalid endpoint IP {ip_text}")
                continue
            if address not in network or address in {network.network_address, network.broadcast_address}:
                errors.append(f"Routing link {name} endpoint {ip_text} is not usable in {network}")
            if ip_text in transit_ips:
                errors.append(f"Duplicate routed transit IP {ip_text}")
            transit_ips.add(ip_text)
        if observed_nodes != expected_nodes:
            errors.append(f"Routing link {name} endpoints must be {sorted(expected_nodes)}")

    for index, (left_name, left) in enumerate(transit_networks):
        for right_name, right in transit_networks[index + 1:]:
            if left.overlaps(right):
                errors.append(f"Routed transit CIDR overlap: {left_name} and {right_name}")

    routes = config.get("routes", {})
    if routes.get("ipsec_l3", {}).get("cryptographic_ipsec") is not False:
        errors.append("ipsec_l3 must explicitly declare cryptographic_ipsec=false")
    if routes.get("ipsec_l3", {}).get("runtime_mode") != "routed_tunnel_abstraction_between_firewalls":
        errors.append("ipsec_l3 must terminate logically on the two firewall abstractions")
    routed_prefixes = {
        str(item.get("prefix"))
        for owner in ("hq_l3_gateway", "telesale_l3_gateway")
        for item in routes.get(owner, {}).get("user_routes", [])
    }
    if "10.10.93.0/24" in routed_prefixes:
        errors.append("VLAN 93 must not be routed through the IPsec abstraction")

    relay = config.get("dhcp_relay", {})
    if relay.get("server_ip") != "10.10.100.10":
        errors.append("DHCP relay must target 10.10.100.10")
    if set(relay.get("hq_vlans", [])) != {93, 101, 103, 104, 110, 120, 140}:
        errors.append("HQ DHCP relay VLAN set is incorrect")
    if set(relay.get("branch_vlans", [])) != {50}:
        errors.append("Branch DHCP relay must exist only on local VLAN 50")


def _validate_policy_and_edges(config: dict[str, Any], model: dict[str, Any], errors: list[str]) -> None:
    isolation = {
        int(item["source_vlan"]): {int(value) for value in item.get("deny_destination_vlans", [])}
        for item in config.get("hq_project_isolation", [])
    }
    for vlan, denied in EXPECTED_PROJECT_ISOLATION.items():
        if isolation.get(vlan) != denied:
            errors.append(f"VLAN {vlan} isolation must deny exactly {sorted(denied)}")

    for policy in config.get("hq_project_isolation", []):
        if set(policy.get("allow_service_hosts", [])) != PROJECT_SERVICE_HOSTS:
            errors.append(f"VLAN {policy.get('source_vlan')} project services are not least-privilege aligned")
        if set(policy.get("deny_internal_prefixes", [])) != INTERNAL_PREFIXES:
            errors.append(f"VLAN {policy.get('source_vlan')} must deny other internal prefixes after explicit allows")

    zones = {int(item["source_vlan"]): item for item in config.get("hq_zone_policies", [])}
    if set(zones) != {120, 140}:
        errors.append("HQ zone policies must cover Guest VLAN 120 and HQ IoT VLAN 140")
    if zones.get(120, {}).get("allow_internet") is not True:
        errors.append("Guest VLAN 120 must be Internet-only after bootstrap service allows")
    if zones.get(140, {}).get("allow_internet") is not False:
        errors.append("HQ IoT VLAN 140 must not receive broad Internet access")

    l2 = config.get("l2vpn_policy", {})
    if int(l2.get("vlan", -1)) != 93 or l2.get("branch_svi_allowed") is not False:
        errors.append("L2VPN policy must make VLAN 93 HQ-gateway-only with no Branch SVI")

    firewall_sites = config.get("firewall_policy", {}).get("sites", {})
    if set(firewall_sites) != {"hq", "branch"}:
        errors.append("Firewall policy sites must be HQ and Branch")
    for site, item in firewall_sites.items():
        if item.get("design_redundancy") != "active_standby":
            errors.append(f"Firewall {site} must be represented as active/standby HA in design")
        if not item.get("tunnel_interface") or "tunnel" not in item.get("runtime_interfaces", {}):
            errors.append(f"Firewall {site} must expose the routed intersite tunnel interface")
        if not item.get("remote_subnets"):
            errors.append(f"Firewall {site} must declare remote corporate subnets")

    provider = model.get("edge_design", {}).get("provider_domain", {}).get("circuits", {})
    expected_provider = {"hq_primary", "hq_backup", "branch_primary", "branch_backup"}
    if set(provider) != expected_provider:
        errors.append("Provider design must contain independent Primary/Backup circuits for HQ and Branch")
    for name, circuit in provider.items():
        sites = list(circuit.get("sites", []))
        if len(sites) != 1:
            errors.append(f"Provider circuit {name} must belong to exactly one physical site")

    handoffs = config.get("provider_handoff_paths", {})
    if set(handoffs) != {"primary", "backup"}:
        errors.append("Provider handoff role plan must contain primary and backup")
    for name, item in handoffs.items():
        if item.get("representation") != "design_only" or item.get("runtime_node") is not None:
            errors.append(f"Provider handoff {name} must remain design-only")

    interfaces = config.get("interfaces", {})
    if any("port-channel" in str(value).lower() for value in interfaces.values()):
        errors.append("Candidate interface mapping must not invent Port-channel without a confirmed physical design")

    sdn = config.get("sdn", {})
    if sdn.get("enabled") is not True:
        errors.append("SDN must be enabled")
    if len(EXPECTED_CONTROLLED_SWITCHES) != 6:
        errors.append("v7 must have exactly six controlled OVS")
    for intent in sdn.get("intents", []):
        if intent.get("allow_destination_vlans") == [100]:
            errors.append(f"SDN intent {intent.get('name')} must not grant broad access to Server VLAN 100")


def validate_all(config: dict[str, Any]) -> list[str]:
    model = load_network_model()
    errors = list(validate_network_model(model))
    _validate_vlans(config, errors)
    _validate_sites_and_devices(config, model, errors)
    _validate_routing(config, model, errors)
    _validate_policy_and_edges(config, model, errors)
    return errors


def main() -> int:
    errors = validate_all(load_vars())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("OK: enterprise v7 variables are internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
