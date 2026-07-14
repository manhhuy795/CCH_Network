from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
NETWORK_MODEL_FILE = REPO_ROOT / "vars" / "network_model.yml"
EXPECTED_HOST_GROUPS = {
    "project_a": {"vlan": 20, "count": 20, "prefix": "h20", "subnet": "172.16.20.0/24", "gateway": "172.16.20.1", "first_ip": "172.16.20.11", "last_ip": "172.16.20.30"},
    "project_b": {"vlan": 30, "count": 20, "prefix": "h30", "subnet": "172.16.30.0/24", "gateway": "172.16.30.1", "first_ip": "172.16.30.11", "last_ip": "172.16.30.30"},
    "project_c": {"vlan": 40, "count": 20, "prefix": "h40", "subnet": "172.16.40.0/24", "gateway": "172.16.40.1", "first_ip": "172.16.40.11", "last_ip": "172.16.40.30"},
    "telesale": {"vlan": 50, "count": 20, "prefix": "h50", "subnet": "172.16.50.0/24", "gateway": "172.16.50.1", "first_ip": "172.16.50.11", "last_ip": "172.16.50.30"},
    "backoffice": {"vlan": 60, "count": 20, "prefix": "h60", "subnet": "172.16.60.0/24", "gateway": "172.16.60.1", "first_ip": "172.16.60.11", "last_ip": "172.16.60.30"},
    "it_support": {"vlan": 70, "count": 10, "prefix": "h70", "subnet": "172.16.70.0/24", "gateway": "172.16.70.1", "first_ip": "172.16.70.11", "last_ip": "172.16.70.20"},
}
EXPECTED_SERVICES = {
    "h90": "172.16.90.10",
    "hzalo": "172.16.200.10",
    "hcall": "172.16.201.10",
    "hsocial": "172.16.202.10",
    "hinternet": "172.16.203.10",
}


def load_network_model(path: Path | None = None) -> dict[str, Any]:
    model_path = path or NETWORK_MODEL_FILE
    return yaml.safe_load(model_path.read_text(encoding="utf-8"))


def build_host_inventory(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    hosts: dict[str, dict[str, Any]] = {}
    for group_name, group in model["host_groups"].items():
        network = ipaddress.ip_network(group["subnet"])
        first_host = int(group.get("first_host", 11))
        for index in range(1, int(group["count"]) + 1):
            name = f"{group['prefix']}_{index:02d}"
            hosts[name] = {
                "name": name,
                "label": f"{group['label']} - User {index:02d}",
                "ip": str(network.network_address + first_host + index - 1),
                "kind": "user",
                "group": group_name,
                "group_label": group["label"],
                "vlan": int(group["vlan"]),
                "site": group["site"],
                "switch": group["switch"],
            }

    for name, service in model["services"].items():
        hosts[name] = {
            "name": name,
            "label": service["label"],
            "ip": service["ip"],
            "kind": "service",
            "group": name,
            "group_label": service["label"],
            "vlan": service.get("vlan"),
            "site": service.get("site", "Internet"),
            "switch": service.get("switch", "internet"),
        }
    return hosts


def validate_network_model(model: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    hosts = build_host_inventory(model)
    user_hosts = [host for host in hosts.values() if host["kind"] == "user"]
    services = [host for host in hosts.values() if host["kind"] == "service"]

    if len(user_hosts) != 110:
        errors.append(f"Network model must define exactly 110 user hosts, found {len(user_hosts)}")
    if len(hosts) != 115:
        errors.append(f"Network model must define exactly 115 endpoints, found {len(hosts)}")
    if int(model.get("host_groups", {}).get("it_support", {}).get("count", 0)) != 10:
        errors.append("IT Support must have exactly 10 users")

    for group_name, expected in EXPECTED_HOST_GROUPS.items():
        group = model.get("host_groups", {}).get(group_name)
        if not group:
            errors.append(f"Missing required host group {group_name}")
            continue
        for key in ("vlan", "count", "prefix", "subnet", "gateway"):
            if group.get(key) != expected[key]:
                errors.append(f"Host group {group_name} {key} must be {expected[key]}, found {group.get(key)}")
        first_name = f"{expected['prefix']}_01"
        last_name = f"{expected['prefix']}_{int(expected['count']):02d}"
        if hosts.get(first_name, {}).get("ip") != expected["first_ip"]:
            errors.append(f"{first_name} must use IP {expected['first_ip']}, found {hosts.get(first_name, {}).get('ip')}")
        if hosts.get(last_name, {}).get("ip") != expected["last_ip"]:
            errors.append(f"{last_name} must use IP {expected['last_ip']}, found {hosts.get(last_name, {}).get('ip')}")

    host_names = [host["name"] for host in hosts.values()]
    duplicate_names = sorted({name for name in host_names if host_names.count(name) > 1})
    if duplicate_names:
        errors.append(f"Duplicate endpoint hostnames found: {duplicate_names}")

    ip_values = [host["ip"] for host in hosts.values()]
    duplicate_ips = sorted({ip for ip in ip_values if ip_values.count(ip) > 1})
    if duplicate_ips:
        errors.append(f"Duplicate endpoint IP addresses found: {duplicate_ips}")

    switches = set(model.get("switches", {}))
    for group_name, group in model.get("host_groups", {}).items():
        switch_name = group.get("switch")
        if switch_name not in switches:
            errors.append(f"Host group {group_name} maps to missing switch {switch_name}")
        try:
            network = ipaddress.ip_network(str(group["subnet"]), strict=True)
            gateway = ipaddress.ip_address(str(group["gateway"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"Host group {group_name} has invalid subnet/gateway: {exc}")
            continue
        if gateway not in network:
            errors.append(f"Host group {group_name} gateway {gateway} is outside {network}")
        group_hosts = [host for host in user_hosts if host["group"] == group_name]
        for host in group_hosts:
            address = ipaddress.ip_address(host["ip"])
            if address not in network:
                errors.append(f"Host {host['name']} IP {address} is outside {network}")
            if address in {network.network_address, network.broadcast_address, gateway}:
                errors.append(f"Host {host['name']} IP {address} conflicts with reserved subnet address")

    for service_name, service in model.get("services", {}).items():
        try:
            service_ip = ipaddress.ip_address(str(service["ip"]))
        except (KeyError, ValueError) as exc:
            errors.append(f"Service {service_name} has invalid IP: {exc}")
            continue
        if service.get("switch") and service["switch"] not in switches:
            errors.append(f"Service {service_name} maps to missing switch {service['switch']}")
        if service.get("subnet") and service_ip not in ipaddress.ip_network(str(service["subnet"]), strict=True):
            errors.append(f"Service {service_name} IP {service_ip} is outside {service['subnet']}")

    for service_name, expected_ip in EXPECTED_SERVICES.items():
        service = model.get("services", {}).get(service_name)
        if not service:
            errors.append(f"Missing required service {service_name}")
        elif service.get("ip") != expected_ip:
            errors.append(f"Service {service_name} must use IP {expected_ip}, found {service.get('ip')}")

    expected_services = set(EXPECTED_SERVICES)
    actual_services = {service["name"] for service in services}
    if actual_services != expected_services:
        errors.append(f"Service endpoints must be {sorted(expected_services)}, found {sorted(actual_services)}")

    node_ids = set(model.get("host_groups", {})) | set(model.get("services", {})) | set(model.get("switches", {})) | set(model.get("infrastructure", {}))
    for index, link in enumerate(model.get("links", []), start=1):
        if len(link) != 3:
            errors.append(f"Topology link #{index} must have [source, target, type], found {link}")
            continue
        source, target, _link_type = link
        if source not in node_ids:
            errors.append(f"Topology link #{index} references missing source node {source}")
        if target not in node_ids:
            errors.append(f"Topology link #{index} references missing target node {target}")

    for group_name, path in model.get("group_paths", {}).items():
        if group_name not in model.get("host_groups", {}):
            errors.append(f"group_paths references missing host group {group_name}")
        for node in path:
            if node not in node_ids:
                errors.append(f"group_paths[{group_name}] references missing node {node}")

    return errors


def controlled_switches(model: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        name
        for name, switch in model["switches"].items()
        if bool(switch.get("controlled"))
    )


def dpid_map(model: dict[str, Any]) -> dict[str, str]:
    return {
        name: switch["dpid"]
        for name, switch in model["switches"].items()
        if switch.get("dpid")
    }


def dpid_name_map(model: dict[str, Any]) -> dict[int, str]:
    return {
        int(switch["dpid"], 16): name
        for name, switch in model["switches"].items()
        if switch.get("dpid")
    }


def architecture_links(model: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [tuple(link) for link in model["links"]]


def user_count(model: dict[str, Any]) -> int:
    return sum(int(group["count"]) for group in model["host_groups"].values())
