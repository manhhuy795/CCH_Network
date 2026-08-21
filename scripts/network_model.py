from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
NETWORK_MODEL_FILE = REPO_ROOT / "vars" / "network_model.yml"

EXPECTED_HOST_GROUPS = {
    "project_a": {"vlan": 20, "count": 20, "prefix": "h20", "subnet": "172.16.20.0/24", "gateway": "172.16.20.1", "site": "hq", "switch": "access_floor1", "first_ip": "172.16.20.11", "last_ip": "172.16.20.30"},
    "project_b": {"vlan": 30, "count": 20, "prefix": "h30", "subnet": "172.16.30.0/24", "gateway": "172.16.30.1", "site": "hq", "switch": "access_floor1", "first_ip": "172.16.30.11", "last_ip": "172.16.30.30"},
    "project_c": {"vlan": 40, "count": 20, "prefix": "h40", "subnet": "172.16.40.0/24", "gateway": "172.16.40.1", "site": "hq", "switch": "access_floor2", "first_ip": "172.16.40.11", "last_ip": "172.16.40.30"},
    "telesale": {"vlan": 50, "count": 20, "prefix": "h50", "subnet": "172.16.50.0/24", "gateway": "172.16.50.1", "site": "branch_telesale", "switch": "access_branch", "first_ip": "172.16.50.11", "last_ip": "172.16.50.30"},
    "backoffice": {"vlan": 60, "count": 20, "prefix": "h60", "subnet": "172.16.60.0/24", "gateway": "172.16.60.1", "site": "hq", "switch": "access_floor2", "first_ip": "172.16.60.11", "last_ip": "172.16.60.30"},
    "it_support": {"vlan": 70, "count": 10, "prefix": "h70", "subnet": "172.16.70.0/24", "gateway": "172.16.70.1", "site": "hq", "switch": "access_floor2", "first_ip": "172.16.70.11", "last_ip": "172.16.70.20"},
}
EXPECTED_SITE_GROUPS = {
    "iot_hq": {"vlan": 110, "subnet": "172.16.110.0/24", "gateway": "172.16.110.1", "site": "hq", "switch": "access_floor1", "kind": "iot"},
    "iot_branch": {"vlan": 111, "subnet": "172.16.111.0/24", "gateway": "172.16.111.1", "site": "branch_telesale", "switch": "access_branch", "kind": "iot"},
    "guest": {"vlan": 120, "subnet": "172.16.120.0/24", "gateway": "172.16.120.1", "site": "hq", "switch": "access_floor1", "kind": "guest"},
}
EXPECTED_SERVICES = {"h90": "172.16.90.10", "hzalo": "172.16.200.10", "hcall": "172.16.201.10", "hsocial": "172.16.202.10", "hinternet": "172.16.203.10"}
EXPECTED_INFRASTRUCTURE_SERVICES = {
    "hdhcp": "172.16.100.10", "hdns": "172.16.100.11", "hntp": "172.16.100.12", "hmonitor": "172.16.100.13",
    "hnvr": "172.16.100.14", "hrecording": "172.16.100.15", "hdialer": "172.16.100.16", "hbackup": "172.16.100.17", "had": "172.16.100.18",
}
EXPECTED_SITES = {"hq", "branch_telesale", "wan", "internet"}
EXPECTED_PHYSICAL_SITES = {"hq", "branch_telesale"}
EXPECTED_CONTROLLED_SWITCHES = {"access_floor1", "access_floor2", "dist_hq_1", "dist_hq_2", "core_hq", "access_branch", "dist_branch", "infra_access"}
EXPECTED_CE_NODES = {"ce_hq", "ce_telesale"}
EXPECTED_FIREWALL_NODES = {"fw_hq", "fw_telesale"}
EXPECTED_WAN_NODES = {"mpls_primary", "mpls_backup"}
EXPECTED_L2VPN_NODE = "l2vpn_vpws40"
FORBIDDEN_TOPOLOGY_NODES = {"access_hq_a", "access_hq_b", "access_hq_c", "access_hq_it", "voice_access", "access_backoffice", "access_iot", "access_guest", "access_branch_old", "dist_branch_old", "ce_branch", "fw_branch", "branch_backoffice", "dist_backoffice", "ce_backoffice", "fw_backoffice"}
EXPECTED_PROVIDER_CIRCUITS = {
    "primary": {"id": "isp_circuit_a", "state": "active", "color": "blue"},
    "backup": {"id": "isp_circuit_b", "state": "standby", "color": "purple"},
}
EXPECTED_EDGE_FIREWALLS = {
    "hq": {"runtime_node": "fw_hq", "design_role": "ha_pair", "inside_node": "core_hq"},
    "branch_telesale": {"runtime_node": "fw_telesale", "design_role": "single_firewall_simulation", "inside_node": "dist_branch"},
}
EXPECTED_SERVER_ZONE_COMPONENTS = {
    "sdn_controller": {"runtime_node": "c0"},
    "dhcp_server": {"runtime_node": "hdhcp"},
    "sbc_voice_edge": {"runtime_node": "h90", "design_role": "dmz_sbc", "runtime_state": "collapsed_voice_placeholder"},
    "pbx_voice_inside": {"runtime_node": "h90", "design_role": "inside_pbx", "runtime_state": "collapsed_voice_placeholder"},
    "monitoring_nms": {"runtime_node": "hmonitor"},
    "database_server": {"runtime_node": None, "runtime_state": "design_only_not_simulated"},
    "it_jump_host_aaa": {"runtime_node": "had", "design_role": "privileged_management"},
}
ALLOWED_LINK_TYPES = {"data", "routed", "mpls", "l2vpn", "control"}


def _model_records(model: dict[str, Any]):
    for category in ("host_groups", "services", "infrastructure_services", "switches", "infrastructure"):
        for name, item in model.get(category, {}).items():
            yield category, str(name), item


def _validate_model_identity_fields(model: dict[str, Any], hosts: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    logical_names: list[str] = []
    runtime_names: list[str] = []
    dpids: list[str] = []
    for category, name, item in _model_records(model):
        logical_names.append(str(item.get("logical_name", name)))
        runtime_name = item.get("runtime_name")
        if runtime_name:
            runtime_names.append(str(runtime_name))
        if category == "switches" and item.get("dpid"):
            dpids.append(str(item["dpid"]).lower())
    runtime_names.extend(runtime_switch_name(model, name) for name in controlled_switches(model))
    if len(logical_names) != len(set(logical_names)):
        errors.append("Duplicate logical names found")
    if len(runtime_names) != len(set(runtime_names)):
        errors.append("Duplicate runtime names found")
    if len(dpids) != len(set(dpids)):
        errors.append("Duplicate DPIDs found across model switches")

    vlan_entries = [(name, int(item["vlan"])) for name, item in model.get("host_groups", {}).items() if item.get("vlan") is not None]
    vlan_values = [value for _, value in vlan_entries]
    if len(vlan_values) != len(set(vlan_values)):
        errors.append("Duplicate host-group VLANs found")

    declared_networks: list[tuple[str, str, ipaddress.IPv4Network]] = []
    for category in ("host_groups", "services", "infrastructure_services"):
        for name, item in model.get(category, {}).items():
            if not item.get("subnet"):
                continue
            try:
                declared_networks.append((category, str(name), ipaddress.ip_network(str(item["subnet"]), strict=False)))
            except ValueError as exc:
                errors.append(f"{category} {name} has invalid subnet: {exc}")
    for index, (left_category, left_name, left) in enumerate(declared_networks):
        for right_category, right_name, right in declared_networks[index + 1:]:
            if not left.overlaps(right):
                continue
            if left_category == right_category == "infrastructure_services" and left == right:
                continue
            errors.append(f"Declared subnet overlap: {left_name} and {right_name}")
    if len(hosts) != len({host["name"] for host in hosts.values()}):
        errors.append("Duplicate runtime endpoint names found")
    return errors


def _validate_edge_design(model: dict[str, Any], node_ids: set[str]) -> list[str]:
    errors: list[str] = []
    edge_design = model.get("edge_design", {})
    provider = edge_design.get("provider_domain", {})
    circuits = provider.get("circuits", {})
    if provider.get("mode") != "logical_provider_demarcation":
        errors.append("edge_design.provider_domain must be logical_provider_demarcation")
    if set(circuits) != set(EXPECTED_PROVIDER_CIRCUITS):
        errors.append(f"Provider circuits must be {sorted(EXPECTED_PROVIDER_CIRCUITS)}")
    circuit_ids: list[str] = []
    for name, expected in EXPECTED_PROVIDER_CIRCUITS.items():
        item = circuits.get(name, {})
        for key, value in expected.items():
            if item.get(key) != value:
                errors.append(f"Provider circuit {name} {key} must be {value!r}")
        if set(item.get("sites", [])) != set(EXPECTED_PHYSICAL_SITES):
            errors.append(f"Provider circuit {name} must serve HQ and Branch Telesale")
        if item.get("representation") != "design_only" or item.get("runtime_node") is not None or item.get("runtime_state") != "design_only" or item.get("controller_managed") is not False:
            errors.append(f"Provider circuit {name} must be explicitly design-only")
        circuit_ids.append(str(item.get("id", "")))
    if len(circuit_ids) != len(set(circuit_ids)):
        errors.append("Provider circuit IDs must be unique")

    firewalls = edge_design.get("firewalls", {})
    if set(firewalls) != set(EXPECTED_EDGE_FIREWALLS):
        errors.append(f"Edge firewall design must cover {sorted(EXPECTED_EDGE_FIREWALLS)}")
    design_only_ids = set(circuit_ids)
    for site, expected in EXPECTED_EDGE_FIREWALLS.items():
        item = firewalls.get(site, {})
        for key, value in expected.items():
            if item.get(key) != value:
                errors.append(f"Edge firewall {site} {key} must be {value!r}")
        if item.get("outside_circuits") != ["primary", "backup"]:
            errors.append(f"Edge firewall {site} must reference primary and backup circuits")
        runtime_node = str(item.get("runtime_node", ""))
        if runtime_node not in EXPECTED_FIREWALL_NODES or runtime_node not in node_ids:
            errors.append(f"Edge firewall {site} must reference an active firewall runtime node")
        for key in ("primary_member", "backup_member"):
            member = item.get(key)
            if member:
                design_only_ids.add(str(member))
        if item.get("representation") != "design_metadata" or item.get("controller_managed") is not False:
            errors.append(f"Edge firewall {site} must be design metadata, not an OpenFlow node")
    if design_only_ids & node_ids:
        errors.append(f"Design-only edge IDs must not become topology nodes: {sorted(design_only_ids & node_ids)}")
    return errors


def _validate_server_zone_design(model: dict[str, Any], node_ids: set[str]) -> list[str]:
    errors: list[str] = []
    design = model.get("server_zone_design", {})
    if design.get("runtime_switch") != "infra_access":
        errors.append("server_zone_design must use infra_access as its runtime switch")
    components = design.get("components", {})
    if set(components) != set(EXPECTED_SERVER_ZONE_COMPONENTS):
        errors.append(f"Server zone design components must be {sorted(EXPECTED_SERVER_ZONE_COMPONENTS)}")
    for name, expected in EXPECTED_SERVER_ZONE_COMPONENTS.items():
        item = components.get(name, {})
        for key, value in expected.items():
            if item.get(key) != value:
                errors.append(f"Server zone component {name} {key} must be {value!r}")
        runtime_node = item.get("runtime_node")
        if runtime_node is not None and runtime_node not in node_ids:
            errors.append(f"Server zone component {name} references missing runtime node {runtime_node}")
        expected_representation = "design_only" if runtime_node is None else "design_metadata"
        if item.get("representation") != expected_representation or item.get("controller_managed") is not False:
            errors.append(f"Server zone component {name} has invalid runtime/design-only annotation")
    if components.get("sbc_voice_edge", {}).get("runtime_node") != components.get("pbx_voice_inside", {}).get("runtime_node"):
        errors.append("SBC and PBX runtime placeholders must be explicitly mapped to the same h90 service")
    return errors


def load_network_model(path: Path | None = None) -> dict[str, Any]:
    model_path = path or NETWORK_MODEL_FILE
    return yaml.safe_load(model_path.read_text(encoding="utf-8"))


def _endpoint_placement(group: dict[str, Any], index: int) -> dict[str, Any]:
    placements = group.get("placements") or []
    cursor = 0
    for placement in placements:
        count = int(placement.get("count", 0))
        if index <= cursor + count:
            return dict(placement)
        cursor += count
    return {
        "switch": group["switch"],
        "site": group.get("site"),
        "floor": group.get("floor"),
    }


def _endpoint_switch(group: dict[str, Any], index: int) -> str:
    return str(_endpoint_placement(group, index)["switch"])


def build_host_inventory(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    hosts: dict[str, dict[str, Any]] = {}
    for group_name, group in model.get("host_groups", {}).items():
        network = ipaddress.ip_network(group["subnet"])
        first_host = int(group.get("first_host", 11))
        explicit_endpoints = list(group.get("endpoints", []))
        endpoints = explicit_endpoints or [
            {"name": f"{group['prefix']}_{index:02d}", "label": f"{group['label']} - User {index:02d}", "ip": str(network.network_address + first_host + index - 1)}
            for index in range(1, int(group.get("count", 0)) + 1)
        ]
        for index, endpoint in enumerate(endpoints, start=1):
            placement = _endpoint_placement(group, index)
            hosts[str(endpoint["name"])] = {
                "name": str(endpoint["name"]),
                "label": str(endpoint.get("label") or f"{group['label']} - Endpoint {index:02d}"),
                "ip": str(endpoint.get("ip") or network.network_address + first_host + index - 1),
                "kind": str(endpoint.get("kind") or group.get("host_kind", "user")),
                "role": endpoint.get("role"),
                "group": group_name,
                "group_label": group["label"],
                "vlan": int(group["vlan"]),
                "site": endpoint.get("site") or placement.get("site") or group["site"],
                "floor": endpoint.get("floor") or placement.get("floor") or group.get("floor") or ("floor1" if _endpoint_switch(group, index) == "access_floor1" else "floor2" if _endpoint_switch(group, index) == "access_floor2" else None),
                "switch": str(endpoint.get("switch") or placement["switch"]),
                "addressing": endpoint.get("addressing") or group.get("addressing", "static"),
            }

    for name, service in model.get("services", {}).items():
        hosts[name] = {"name": name, "label": service["label"], "ip": service["ip"], "kind": "service", "group": name, "group_label": service["label"], "vlan": service.get("vlan"), "site": service.get("site", "internet"), "switch": service.get("switch", "internet_zone")}
    for name, service in model.get("infrastructure_services", {}).items():
        hosts[name] = {"name": name, "label": service["label"], "ip": service["ip"], "kind": "infrastructure_service", "role": service.get("role"), "group": "infrastructure_services", "group_label": "Infrastructure Services", "vlan": int(service["vlan"]), "site": service.get("site", "hq"), "switch": service.get("switch", "infra_access"), "addressing": service.get("addressing", "static")}
    return hosts


def _all_node_categories(model: dict[str, Any]) -> dict[str, set[str]]:
    return {"host_groups": set(model.get("host_groups", {})), "services": set(model.get("services", {})), "infrastructure_services": set(model.get("infrastructure_services", {})), "switches": set(model.get("switches", {})), "infrastructure": set(model.get("infrastructure", {}))}


def validate_network_model(model: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    hosts = build_host_inventory(model)
    errors.extend(_validate_model_identity_fields(model, hosts))
    users = [host for host in hosts.values() if host["kind"] == "user"]
    services = [host for host in hosts.values() if host["kind"] == "service"]
    if len(users) != 110:
        errors.append(f"Network model must define exactly 110 user hosts, found {len(users)}")
    if len(services) != 5:
        errors.append(f"Network model must define exactly 5 services, found {len(services)}")
    if len(hosts) != 133:
        errors.append(f"Network model must define exactly 133 endpoints, found {len(hosts)}")
    if len(model.get("host_groups", {}).get("it_support", {}).get("endpoints", [])) == 0 and int(model.get("host_groups", {}).get("it_support", {}).get("count", 0)) != 10:
        errors.append("IT Support must have exactly 10 users")
    if set(model.get("sites", {})) != EXPECTED_SITES:
        errors.append(f"Sites must be {sorted(EXPECTED_SITES)}")
    if {name for name, item in model.get("sites", {}).items() if item.get("kind") == "physical"} != EXPECTED_PHYSICAL_SITES:
        errors.append(f"Physical sites must be {sorted(EXPECTED_PHYSICAL_SITES)}")

    for group_name, expected in {**EXPECTED_HOST_GROUPS, **EXPECTED_SITE_GROUPS}.items():
        group = model.get("host_groups", {}).get(group_name)
        if not group:
            errors.append(f"Missing required host group {group_name}")
            continue
        for key in ("vlan", "subnet", "gateway", "site", "switch"):
            if group.get(key) != expected[key]:
                errors.append(f"Host group {group_name} {key} must be {expected[key]}, found {group.get(key)}")
        if group_name in EXPECTED_HOST_GROUPS and int(group.get("count", 0)) != expected["count"]:
            errors.append(f"Host group {group_name} count must be {expected['count']}")
        if group_name in EXPECTED_SITE_GROUPS and group.get("host_kind") != expected["kind"]:
            errors.append(f"Host group {group_name} host_kind must be {expected['kind']}")
        network = ipaddress.ip_network(str(group.get("subnet", "0.0.0.0/32")), strict=True)
        gateway = ipaddress.ip_address(str(group.get("gateway", "0.0.0.0")))
        if gateway not in network:
            errors.append(f"Host group {group_name} gateway is outside subnet")
        for host in hosts.values():
            if host["group"] != group_name:
                continue
            if ipaddress.ip_address(host["ip"]) not in network:
                errors.append(f"Host {host['name']} is outside {network}")

    host_names = list(hosts)
    ips = [str(host["ip"]) for host in hosts.values()]
    if len(host_names) != len(set(host_names)):
        errors.append("Duplicate endpoint hostnames found")
    if len(ips) != len(set(ips)):
        errors.append("Duplicate endpoint IP addresses found")

    switches = model.get("switches", {})
    controlled = {name for name, item in switches.items() if item.get("controlled")}
    if controlled != EXPECTED_CONTROLLED_SWITCHES:
        errors.append(f"Controlled OpenFlow switches must be {sorted(EXPECTED_CONTROLLED_SWITCHES)}, found {sorted(controlled)}")
    dpids = [str(item.get("dpid", "")) for item in switches.values() if item.get("controlled")]
    if len(dpids) != len(set(dpids)):
        errors.append("Duplicate switch DPIDs found")
    runtime_names = [runtime_switch_name(model, name) for name in controlled]
    if len(runtime_names) != len(set(runtime_names)):
        errors.append("Duplicate controlled OVS runtime names found")
    for name in controlled:
        dpid = str(switches[name].get("dpid", ""))
        if len(dpid) != 16 or any(char not in "0123456789abcdefABCDEF" for char in dpid):
            errors.append(f"Controlled switch {name} has invalid DPID")
        if len(runtime_switch_name(model, name).encode("ascii", errors="ignore")) > 15:
            errors.append(f"Runtime switch name exceeds Linux interface limit: {name}")

    categories = _all_node_categories(model)
    occurrences: dict[str, list[str]] = {}
    for category, names in categories.items():
        for name in names:
            occurrences.setdefault(name, []).append(category)
    duplicate_nodes = {name: kinds for name, kinds in occurrences.items() if len(kinds) > 1}
    if duplicate_nodes:
        errors.append(f"Duplicate topology node IDs across categories: {duplicate_nodes}")
    node_ids = set().union(*categories.values())
    errors.extend(_validate_edge_design(model, node_ids))
    errors.extend(_validate_server_zone_design(model, node_ids))
    forbidden = sorted(node_ids & FORBIDDEN_TOPOLOGY_NODES)
    if forbidden:
        errors.append(f"Legacy or retired topology nodes are forbidden: {forbidden}")

    infrastructure = model.get("infrastructure", {})
    if {name for name, item in infrastructure.items() if item.get("type") == "router"} != EXPECTED_CE_NODES:
        errors.append(f"CE nodes must be {sorted(EXPECTED_CE_NODES)}")
    if {name for name, item in infrastructure.items() if item.get("type") == "firewall"} != EXPECTED_FIREWALL_NODES:
        errors.append(f"Firewall nodes must be {sorted(EXPECTED_FIREWALL_NODES)}")
    if {name for name, item in infrastructure.items() if item.get("type") == "wan"} != EXPECTED_WAN_NODES:
        errors.append(f"WAN clouds must be {sorted(EXPECTED_WAN_NODES)}")
    l2vpn_node = infrastructure.get(EXPECTED_L2VPN_NODE, {})
    if l2vpn_node.get("type") != "l2vpn" or l2vpn_node.get("controller_managed") is not False:
        errors.append("l2vpn_vpws40 must be an unmanaged logical L2VPN runtime node")
    if set(model.get("infrastructure_services", {})) != set(EXPECTED_INFRASTRUCTURE_SERVICES):
        errors.append(f"Infrastructure services must be {sorted(EXPECTED_INFRASTRUCTURE_SERVICES)}")

    edges: set[frozenset[str]] = set()
    for index, link in enumerate(model.get("links", []), 1):
        if len(link) != 3:
            errors.append(f"Topology link #{index} must be [source, target, type]")
            continue
        source, target, kind = link
        if source not in node_ids or target not in node_ids:
            errors.append(f"Topology link #{index} references missing endpoint")
        if kind not in ALLOWED_LINK_TYPES:
            errors.append(f"Topology link #{index} has invalid type {kind!r}")
        edge = frozenset((source, target))
        if edge in edges:
            errors.append(f"Duplicate topology link between {source} and {target}")
        edges.add(edge)

    required_edges = {
        ("access_floor1", "dist_hq_1"), ("access_floor2", "dist_hq_2"), ("dist_hq_1", "core_hq"), ("dist_hq_2", "core_hq"),
        ("access_branch", "dist_branch"), ("dist_branch", "ce_telesale"), ("core_hq", "ce_hq"),
        ("ce_hq", "mpls_primary"), ("mpls_primary", "ce_telesale"), ("ce_hq", "mpls_backup"), ("mpls_backup", "ce_telesale"),
        ("dist_hq_2", "l2vpn_vpws40"), ("l2vpn_vpws40", "dist_branch"),
        ("core_hq", "fw_hq"), ("dist_branch", "fw_telesale"), ("fw_hq", "internet_zone"), ("fw_telesale", "internet_zone"),
    }
    for source, target in required_edges:
        if frozenset((source, target)) not in edges:
            errors.append(f"Missing required topology link {source}<->{target}")
    for firewall in EXPECTED_FIREWALL_NODES:
        firewall_edges = [edge for edge in edges if firewall in edge]
        if len(firewall_edges) != 2:
            errors.append(f"{firewall} must have one inside and one outside link")

    project_c = model.get("host_groups", {}).get("project_c", {})
    project_c_placements = project_c.get("placements", [])
    expected_project_c_placements = [
        {"site": "hq", "floor": "floor2", "switch": "access_floor2", "count": 10},
        {"site": "branch_telesale", "switch": "access_branch", "count": 10},
    ]
    if project_c_placements != expected_project_c_placements:
        errors.append("Project C must place 10 VLAN 40 users at HQ and 10 at Branch Telesale")
    project_c_hosts = [host for host in hosts.values() if host.get("group") == "project_c"]
    if {site: sum(host.get("site") == site for host in project_c_hosts) for site in EXPECTED_PHYSICAL_SITES} != {"hq": 10, "branch_telesale": 10}:
        errors.append("Project C runtime inventory must contain 10 endpoints at each physical site")
    l2vpn = model.get("l2vpn_services", {}).get("vlan40_project_c", {})
    if (
        l2vpn.get("service_type") != "vpws"
        or int(l2vpn.get("customer_vlan", -1)) != 40
        or l2vpn.get("gateway_site") != "hq"
        or l2vpn.get("gateway_node") != "core_hq"
        or l2vpn.get("runtime_mode") != "transparent_linux_bridge"
    ):
        errors.append("VLAN 40 L2VPN must be VPWS with a centralized HQ gateway and transparent bridge runtime")
    if l2vpn.get("presentation_path") != ["dist_hq_2", "ce_hq", "l2vpn_vpws40", "ce_telesale", "dist_branch"]:
        errors.append("VLAN 40 presentation path must traverse both CE attachment demarcations")
    attachment_circuits = l2vpn.get("attachment_circuits", {})
    expected_attachment_nodes = {"hq": ("dist_hq_2", "ce_hq"), "branch_telesale": ("dist_branch", "ce_telesale")}
    for site, (customer_switch, ce_node) in expected_attachment_nodes.items():
        attachment = attachment_circuits.get(site, {})
        if attachment.get("customer_switch") != customer_switch or attachment.get("ce_node") != ce_node or int(attachment.get("vlan", -1)) != 40:
            errors.append(f"VLAN 40 attachment circuit {site} must map {customer_switch} to {ce_node}")
    site_paths = model.get("site_group_paths", {}).get("project_c", {})
    if set(site_paths) != EXPECTED_PHYSICAL_SITES or "l2vpn_vpws40" not in site_paths.get("branch_telesale", []):
        errors.append("Project C must declare HQ and Branch site paths through l2vpn_vpws40")

    for group_name, group in model.get("host_groups", {}).items():
        all_switches = {str(group.get("switch")), *(str(item.get("switch")) for item in group.get("placements", []))}
        for switch in all_switches:
            if switch not in switches:
                errors.append(f"Host group {group_name} maps to missing switch {switch}")
        path = model.get("group_paths", {}).get(group_name, [])
        if not path:
            errors.append(f"Missing group path for {group_name}")
        for node in path:
            if node not in node_ids:
                errors.append(f"group_paths[{group_name}] references missing node {node}")

    for service_name, expected_ip in EXPECTED_SERVICES.items():
        service = model.get("services", {}).get(service_name)
        if not service or service.get("ip") != expected_ip:
            errors.append(f"Service {service_name} must use IP {expected_ip}")
    for service_name, expected_ip in EXPECTED_INFRASTRUCTURE_SERVICES.items():
        service = model.get("infrastructure_services", {}).get(service_name, {})
        if service.get("ip") != expected_ip or service.get("vlan") != 100 or service.get("switch") != "infra_access":
            errors.append(f"Infrastructure service {service_name} must use VLAN 100 on infra_access")

    # Business subnets must be unique; VLAN 100 infrastructure services intentionally share one subnet.
    networks: list[tuple[str, ipaddress.IPv4Network]] = []
    for name, group in model.get("host_groups", {}).items():
        networks.append((name, ipaddress.ip_network(group["subnet"])))
    for index, (left_name, left) in enumerate(networks):
        for right_name, right in networks[index + 1:]:
            if left.overlaps(right):
                errors.append(f"Host subnet overlap: {left_name} and {right_name}")
    return errors


def controlled_switches(model: dict[str, Any]) -> tuple[str, ...]:
    return tuple(name for name, switch in model.get("switches", {}).items() if switch.get("controlled"))


def dpid_map(model: dict[str, Any]) -> dict[str, str]:
    return {name: switch["dpid"] for name, switch in model.get("switches", {}).items() if switch.get("dpid")}


def dpid_name_map(model: dict[str, Any]) -> dict[int, str]:
    return {int(switch["dpid"], 16): name for name, switch in model.get("switches", {}).items() if switch.get("dpid")}


def controller_dpid_name_map(model: dict[str, Any]) -> dict[int, str]:
    return {int(switch["dpid"], 16): name for name, switch in model.get("switches", {}).items() if switch.get("controlled") and switch.get("dpid")}


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
    return [tuple(link) for link in model.get("links", [])]


def user_count(model: dict[str, Any]) -> int:
    return sum(int(group.get("count", 0)) for group in model.get("host_groups", {}).values() if group.get("host_kind", "user") == "user")
