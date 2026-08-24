from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
NETWORK_MODEL_FILE = REPO_ROOT / "vars" / "network_model.yml"
EXPECTED_SITES = {"hq", "branch", "wan", "internet"}
EXPECTED_PHYSICAL_SITES = {"hq", "branch"}
EXPECTED_CONTROLLED_SWITCHES = {
    "access_floor1", "access_floor2", "core_hq", "access_branch", "dist_branch", "infra_access"
}
EXPECTED_CE_NODES = {"ce_hq1", "ce_hq2", "ce_branch1", "ce_branch2"}
EXPECTED_FIREWALL_NODES = {"fw_hq", "fw_telesale"}
EXPECTED_WAN_NODES = {"ipsec_l3"}
EXPECTED_L2VPN_NODES = {"l2vpn_primary", "l2vpn_backup"}
EXPECTED_L2VPN_NODE = "l2vpn_primary"  # compatibility alias
ALLOWED_LINK_TYPES = {"data", "routed", "l2vpn", "control"}


def load_network_model(path: Path | None = None) -> dict[str, Any]:
    model_path = path or NETWORK_MODEL_FILE
    payload = yaml.safe_load(model_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{model_path} must contain a YAML mapping")
    return payload


def _endpoint_placement(group: dict[str, Any], index: int) -> dict[str, Any]:
    cursor = 0
    for placement in group.get("placements") or []:
        count = int(placement.get("count", 0))
        if index <= cursor + count:
            return dict(placement)
        cursor += count
    return {"switch": group["switch"], "site": group.get("site"), "floor": group.get("floor")}


def build_host_inventory(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    hosts: dict[str, dict[str, Any]] = {}
    for group_name, group in model.get("host_groups", {}).items():
        network = ipaddress.ip_network(str(group["subnet"]))
        first_host = int(group.get("first_host", 11))
        endpoints = list(group.get("endpoints", []))
        if not endpoints:
            endpoints = [
                {
                    "name": f"{group['prefix']}_{index:02d}",
                    "label": f"{group['label']} - User {index:02d}",
                    "ip": str(network.network_address + first_host + index - 1),
                }
                for index in range(1, int(group.get("count", 0)) + 1)
            ]
        for index, endpoint in enumerate(endpoints, start=1):
            placement = _endpoint_placement(group, index)
            name = str(endpoint["name"])
            hosts[name] = {
                "name": name,
                "label": str(endpoint.get("label") or f"{group['label']} - Endpoint {index:02d}"),
                "ip": str(endpoint.get("ip") or network.network_address + first_host + index - 1),
                "kind": str(endpoint.get("kind") or group.get("host_kind", "user")),
                "role": endpoint.get("role"),
                "group": str(group_name),
                "group_label": str(group["label"]),
                "vlan": int(group["vlan"]),
                "site": str(endpoint.get("site") or placement.get("site") or group.get("site")),
                "switch": str(endpoint.get("switch") or placement.get("switch") or group["switch"]),
                "floor": endpoint.get("floor") or placement.get("floor") or group.get("floor"),
                "addressing": str(group.get("addressing", "static")),
            }

    for name, service in model.get("services", {}).items():
        hosts[name] = {
            "name": name,
            "label": service["label"],
            "ip": service["ip"],
            "kind": "service",
            "role": service.get("zone", "service"),
            "group": "services",
            "group_label": "Internet / Partner Services",
            "vlan": service.get("vlan"),
            "site": service.get("site", "internet"),
            "switch": service.get("switch"),
            "addressing": "static",
        }
    for name, service in model.get("infrastructure_services", {}).items():
        hosts[name] = {
            "name": name,
            "label": service["label"],
            "ip": service["ip"],
            "kind": "infrastructure_service",
            "role": service.get("role"),
            "group": "infrastructure_services",
            "group_label": "Infrastructure Services",
            "vlan": int(service["vlan"]),
            "site": service.get("site", "hq"),
            "switch": service.get("switch", "infra_access"),
            "addressing": service.get("addressing", "static"),
        }
    return hosts


def controlled_switches(model: dict[str, Any]) -> tuple[str, ...]:
    return tuple(name for name, item in model.get("switches", {}).items() if item.get("controlled"))


def dpid_map(model: dict[str, Any]) -> dict[str, str]:
    return {name: str(item["dpid"]) for name, item in model.get("switches", {}).items() if item.get("dpid")}


def dpid_name_map(model: dict[str, Any]) -> dict[int, str]:
    return {int(value, 16): name for name, value in dpid_map(model).items()}


def controller_dpid_name_map(model: dict[str, Any]) -> dict[int, str]:
    controlled = set(controlled_switches(model))
    return {dpid: name for dpid, name in dpid_name_map(model).items() if name in controlled}


def runtime_switch_name(model: dict[str, Any], logical_name: str) -> str:
    return str(model.get("switches", {}).get(logical_name, {}).get("runtime_name", logical_name))


def runtime_switch_map(model: dict[str, Any]) -> dict[str, str]:
    return {name: runtime_switch_name(model, name) for name in controlled_switches(model)}


def enforcement_switch_for_group(model: dict[str, Any], group_name: str) -> str:
    path = list(model.get("group_paths", {}).get(group_name, []))
    if not path:
        raise ValueError(f"Host group {group_name} has no group path")
    for node in reversed(path):
        if model.get("switches", {}).get(node, {}).get("controlled"):
            return str(node)
    raise ValueError(f"Host group {group_name} has no controlled enforcement switch")


def enforcement_switches(model: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted({enforcement_switch_for_group(model, name) for name in model.get("host_groups", {})}))


def architecture_links(model: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [tuple(str(value) for value in link[:3]) for link in model.get("links", [])]


def endpoint_link_segments(model: dict[str, Any], group_name: str, access_switch: str) -> list[tuple[str, str]]:
    return [
        (str(endpoint["name"]), access_switch)
        for endpoint in build_host_inventory(model).values()
        if endpoint.get("group") == group_name and endpoint.get("switch") == access_switch
    ]


def user_count(model: dict[str, Any]) -> int:
    return sum(
        int(group.get("count", 0))
        for group in model.get("host_groups", {}).values()
        if group.get("host_kind", "user") == "user"
    )


def _all_node_ids(model: dict[str, Any]) -> set[str]:
    nodes: set[str] = set()
    for category in ("host_groups", "services", "infrastructure_services", "switches", "infrastructure"):
        nodes.update(str(name) for name in model.get(category, {}))
    return nodes


def validate_network_model(model: dict[str, Any]) -> list[str]:
    """Validate stable enterprise-v7 invariants without copying the YAML into Python."""
    errors: list[str] = []
    if set(model.get("sites", {})) != EXPECTED_SITES:
        errors.append(f"Sites must be exactly {sorted(EXPECTED_SITES)}")
    physical = {name for name, item in model.get("sites", {}).items() if item.get("kind") == "physical"}
    if physical != EXPECTED_PHYSICAL_SITES:
        errors.append(f"Physical sites must be {sorted(EXPECTED_PHYSICAL_SITES)}")
    if set(controlled_switches(model)) != EXPECTED_CONTROLLED_SWITCHES:
        errors.append(f"Controlled switches must be {sorted(EXPECTED_CONTROLLED_SWITCHES)}")

    infra = model.get("infrastructure", {})
    if not EXPECTED_CE_NODES.issubset(infra):
        errors.append("Two CE nodes per site are required")
    if not EXPECTED_L2VPN_NODES.issubset(infra):
        errors.append("Primary and backup L2VPN nodes are required")
    if not EXPECTED_FIREWALL_NODES.issubset(infra):
        errors.append("HQ and Branch firewall abstractions are required")
    if infra.get("ipsec_l3", {}).get("cryptographic_ipsec") is not False:
        errors.append("ipsec_l3 must explicitly be a non-cryptographic lab abstraction")

    shared = model.get("host_groups", {}).get("project_2", {})
    if int(shared.get("vlan", -1)) != 93 or shared.get("subnet") != "10.10.93.0/24":
        errors.append("Project 2 must be VLAN 93 / 10.10.93.0/24")
    if shared.get("gateway") != "10.10.93.1" or shared.get("gateway_site") != "hq":
        errors.append("VLAN 93 gateway must be 10.10.93.1 at HQ")
    placements = shared.get("placements") or []
    if {item.get("site") for item in placements} != {"hq", "branch"}:
        errors.append("Project 2 VLAN 93 must have HQ and Branch placements")

    l2vpn = model.get("l2vpn_services", {}).get("vlan93_project_2", {})
    if int(l2vpn.get("customer_vlan", -1)) != 93 or l2vpn.get("gateway_site") != "hq":
        errors.append("vlan93_project_2 contract is invalid")
    if l2vpn.get("primary", {}).get("state") != "active" or l2vpn.get("backup", {}).get("state") != "standby":
        errors.append("L2VPN primary must be active and backup must be standby")

    branch_path = model.get("site_group_paths", {}).get("project_2", {}).get("branch", [])
    if "l2vpn_primary" not in branch_path or "ipsec_l3" in branch_path:
        errors.append("Branch Project 2 path must use L2VPN, not IPsec")

    ipsec_design = model.get("edge_design", {}).get("ipsec", {})
    if ipsec_design.get("runtime_path") != ["fw_hq", "ipsec_l3", "fw_telesale"]:
        errors.append("Routed intersite abstraction must terminate on both firewall namespaces")

    node_ids = _all_node_ids(model)
    seen: set[frozenset[str]] = set()
    for raw in model.get("links", []):
        if not isinstance(raw, list) or len(raw) != 3:
            errors.append(f"Invalid topology link {raw!r}")
            continue
        left, right, kind = map(str, raw)
        if left not in node_ids or right not in node_ids:
            errors.append(f"Link references missing node: {left}-{right}")
        if kind not in ALLOWED_LINK_TYPES:
            errors.append(f"Unsupported link type {kind} on {left}-{right}")
        key = frozenset((left, right))
        if key in seen:
            errors.append(f"Duplicate logical link {left}-{right}")
        seen.add(key)

    hosts = build_host_inventory(model)
    ips: set[str] = set()
    for name, host in hosts.items():
        try:
            address = ipaddress.ip_address(str(host["ip"]))
        except ValueError:
            errors.append(f"Invalid endpoint IP for {name}: {host.get('ip')}")
            continue
        if str(address) in ips:
            errors.append(f"Duplicate endpoint IP {address}")
        ips.add(str(address))

    if user_count(model) != 90:
        errors.append(f"Runtime corporate user count must be 90, found {user_count(model)}")
    return errors
