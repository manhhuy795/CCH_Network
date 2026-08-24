from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from . import mininet_control
from .live_mininet import firewall_inventory, phase44_runtime_status
from scripts.common import load_vars
from scripts.network_model import build_host_inventory, controlled_switches, load_network_model, runtime_switch_map, runtime_switch_name
from sdn_mpls_demo.policy_engine import PolicyEngine


ROOT = Path(__file__).resolve().parents[3]
MODEL = load_network_model()
ENGINE = PolicyEngine(ROOT / "sdn_mpls_demo" / "policy.yml")
SOURCE_TRUTH = load_vars()


def _design_node(node_id: str, label: str, node_type: str, site: str, runtime_node: str | None = None) -> dict:
    return {
        "id": node_id,
        "logical_name": node_id,
        "label": label,
        "type": node_type,
        "role": node_type,
        "site": site,
        "runtime_node": runtime_node,
        "runtime_state": "design_only",
        "representation": "design_only",
        "controller_managed": False,
        "status": "design_only",
        "status_source": "source_of_truth",
        "runtime_bridge": None,
    }


def _topology_contract() -> dict:
    edge = deepcopy(MODEL.get("edge_design", {}))
    routing_handoffs = deepcopy(SOURCE_TRUTH.get("provider_handoff_paths", {}))
    design_nodes: list[dict] = []
    for key, circuit in edge.get("provider_domain", {}).get("circuits", {}).items():
        design_nodes.append(_design_node(str(circuit.get("id", key)), str(circuit.get("label", key)), "provider_circuit", "wan"))
    for site, firewall in edge.get("firewalls", {}).items():
        for key in ("primary_member", "backup_member"):
            member = firewall.get(key)
            if member:
                design_nodes.append(_design_node(str(member), str(member), "firewall_peer", site, str(firewall.get("runtime_node"))))
    for site, pair in edge.get("ce_pairs", {}).items():
        for member in pair.get("members", []):
            design_nodes.append(_design_node(str(member), str(member), "ce_design_member", site, str(member)))
    return {
        "source_of_truth": [
            "vars/network_model.yml",
            "vars/vlans.yml",
            "vars/routing.yml",
            "vars/firewall_policies.yml",
        ],
        "runtime_authority": "Mininet Control Agent + live OVS/nftables evidence",
        "design_only_is_runtime": False,
        "provider_domain": deepcopy(edge.get("provider_domain", {})),
        "provider_handoff_paths": routing_handoffs,
        "firewall_redundancy": deepcopy(edge.get("firewalls", {})),
        "server_zone": deepcopy(MODEL.get("server_zone_design", {})),
        "design_nodes": design_nodes,
        "simulation_boundaries": {
            "collapsed_core": "one controlled OVS represents each Core/Distribution HA pair",
            "firewall_ha": "one nftables namespace represents the active HA cluster per site",
            "mpls_l2vpn": "transparent Ethernet bridge abstraction; no PE/P label/control plane",
            "ipsec": "routed tunnel abstraction; no IKE/ESP/XFRM evidence",
        },
    }


def _policy_map() -> dict:
    selectable = [*ENGINE.groups, *ENGINE.services, *ENGINE.infrastructure_services]
    representatives: dict[str, str] = {}
    for group_name in ENGINE.groups:
        host = next((item for item in ENGINE.hosts.values() if item.get("group") == group_name), None)
        if host:
            representatives[group_name] = str(host["name"])
    representatives.update({name: name for name in ENGINE.services})
    representatives.update({name: name for name in ENGINE.infrastructure_services})
    labels = {
        **{name: item["label"] for name, item in ENGINE.groups.items()},
        **{name: item["label"] for name, item in ENGINE.services.items()},
        **{name: item["label"] for name, item in ENGINE.infrastructure_services.items()},
    }
    result: dict[str, dict] = {}
    for source in selectable:
        source_endpoint = representatives.get(source)
        if not source_endpoint:
            continue
        allow: list[str] = []
        deny: list[str] = []
        notes: dict[str, str] = {}
        for destination in selectable:
            if destination == source:
                continue
            destination_endpoint = representatives.get(destination)
            if not destination_endpoint:
                continue
            decision = ENGINE.decide(source_endpoint, destination_endpoint)
            (allow if decision["action"] == "allow" else deny).append(destination)
            notes[destination] = decision["reason"]
        result[source] = {"title": labels.get(source, source), "allow": allow, "deny": deny, "notes": notes}
    return result


def get_topology() -> dict:
    model = load_network_model()
    engine = PolicyEngine(ROOT / "sdn_mpls_demo" / "policy.yml")
    inventory = build_host_inventory(model)
    link_status = mininet_control.get_link_status()
    live = mininet_control.live_status()
    runtime_links = link_status.get("links", {}) if link_status.get("ok") else {}
    bridges = live.get("bridges", {}) if isinstance(live.get("bridges"), dict) else {}

    hosts = sorted(inventory.values(), key=lambda item: (item["kind"] != "user", item["name"]))
    groups: list[dict] = []
    nodes: list[dict] = []
    for name, group in engine.groups.items():
        group_hosts = [host for host in hosts if host.get("group") == name]
        node = {
            "id": name,
            "label": group["label"],
            "type": "user_group" if group.get("host_kind", "user") == "user" else "endpoint_group",
            "site": group.get("site"),
            "sites": sorted({str(host.get("site")) for host in group_hosts}),
            "vlan": int(group["vlan"]),
            "count": int(group["count"]),
            "subnet": group["subnet"],
            "switch": group["switch"],
            "placements": deepcopy(group.get("placements", [])),
            "addressing": group.get("addressing", "static"),
            "hosts": group_hosts,
        }
        groups.append(node)
        nodes.append(node)

    devices: list[dict] = []
    controlled = set(controlled_switches(model))
    for name, switch in model.get("switches", {}).items():
        runtime_name = runtime_switch_name(model, name)
        status = "unknown"
        if live.get("ok"):
            status = "online" if bridges.get(name) or bridges.get(runtime_name) else "offline"
        device = {
            "id": name,
            "logical_name": name,
            "label": switch["label"],
            "type": "switch",
            "role": switch.get("role", "switch"),
            "site": switch.get("site"),
            "dpid": switch.get("dpid"),
            "runtime_bridge": runtime_name,
            "controller_managed": name in controlled,
            "representation": "runtime",
            "status": status,
            "status_source": "mininet_control_agent",
        }
        devices.append(device)
        nodes.append(device)

    for name, item in model.get("infrastructure", {}).items():
        if name == "c0":
            node_type = "controller"
        else:
            node_type = item.get("type", "infrastructure")
        device = {
            "id": name,
            "logical_name": name,
            "label": item["label"],
            "type": node_type,
            "role": item.get("role", node_type),
            "site": item.get("site"),
            "runtime_bridge": item.get("runtime_name"),
            "controller_managed": False,
            "representation": "runtime",
            "status": "online" if live.get("ok") else "unknown",
            "status_source": "mininet_control_agent",
        }
        devices.append(device)
        nodes.append(device)

    for name, service in engine.services.items():
        nodes.append({
            "id": name,
            "logical_name": name,
            "label": service["label"],
            "type": "blocked_service" if name == "hsocial" else "service",
            "site": service.get("site", "internet"),
            "ip": service["ip"],
            "controller_managed": False,
            "status": "online" if live.get("hosts", {}).get(name) else "unknown",
            "status_source": "mininet_control_agent",
        })
    for name, service in engine.infrastructure_services.items():
        nodes.append({
            "id": name,
            "logical_name": name,
            "label": service["label"],
            "type": "infrastructure_service",
            "site": service.get("site", "hq"),
            "ip": service["ip"],
            "vlan": int(service["vlan"]),
            "role": service.get("role"),
            "controller_managed": False,
            "status": "online" if live.get("hosts", {}).get(name) else "unknown",
            "status_source": "mininet_control_agent",
        })

    links = [
        {
            "id": f"{source}-{target}",
            "source": source,
            "target": target,
            "type": kind,
            "status": runtime_links.get(f"{source}-{target}", "unknown" if link_status.get("ok") else "unknown"),
        }
        for source, target, kind in model.get("links", [])
    ]

    sites = []
    for site_id in ("hq", "branch"):
        sites.append({
            "id": site_id,
            "label": model["sites"][site_id]["label"],
            "kind": "physical",
            "source_id": site_id,
            "groups": [group["id"] for group in groups if site_id in group.get("sites", [group.get("site")])],
            "devices": [device["logical_name"] for device in devices if device.get("site") == site_id],
        })

    contract = _topology_contract()
    l2 = deepcopy(model["l2vpn_services"]["vlan93_project_2"])
    return {
        "nodes": nodes,
        "groups": groups,
        "hosts": hosts,
        "links": links,
        "metadata": deepcopy(model.get("metadata", {})),
        "sites": sites,
        "site_ids": ["hq", "branch"],
        "devices": devices,
        "logical_switches": [item for item in devices if item.get("controller_managed")],
        "runtime_bridge_map": runtime_switch_map(model),
        "ce_nodes": [item for item in devices if item.get("type") == "ce_bridge"],
        "firewalls": firewall_inventory(),
        "topology_contract": contract,
        "design_nodes": deepcopy(contract["design_nodes"]),
        "mpls": {
            "service_type": "L2VPN",
            "primary": {"id": "l2vpn_primary", "status": runtime_links.get("ce_hq1-l2vpn_primary", "unknown")},
            "backup": {"id": "l2vpn_backup", "status": runtime_links.get("ce_hq2-l2vpn_backup", "unknown")},
            "controller_managed": False,
        },
        "l2vpn": {
            "service": "vlan93_project_2",
            "type": "VPWS / E-Line logic",
            "customer_vlan": 93,
            "sites": ["hq", "branch"],
            "gateway_site": "hq",
            "gateway_node": "core_hq",
            "gateway": "10.10.93.1",
            "primary": deepcopy(l2.get("primary", {})),
            "backup": deepcopy(l2.get("backup", {})),
            "runtime_mode": l2.get("runtime_mode"),
            "simulation_scope": "Transparent Ethernet behavior; no PE/P labels or provider signaling",
        },
        "ipsec": {
            "id": "ipsec_l3",
            "runtime_mode": "routed_tunnel_abstraction",
            "cryptographic_ipsec": False,
            "simulation_scope": "Route/path behavior only; no IKE/ESP/XFRM proof",
        },
        "internet_zone": {"id": "internet_zone", "status": "logical_runtime", "controller_managed": False},
        "phase44_runtime": phase44_runtime_status(),
        "policy_map": _policy_map(),
        "summary": {
            "user_count": sum(host["kind"] == "user" for host in hosts),
            "service_count": len(engine.services),
            "endpoint_count": len(hosts),
            "iot_hq_count": sum(host.get("group") == "iot_hq" for host in hosts),
            "iot_branch_count": sum(host.get("group") == "iot_branch" for host in hosts),
            "guest_count": sum(host.get("kind") == "guest" for host in hosts),
            "infrastructure_service_count": len(engine.infrastructure_services),
            "controlled_ovs_count": len(controlled),
            "site_count": 2,
            "ce_count": 4,
            "firewall_count": 2,
            "l2vpn_service_count": 1,
            "live_link_control": bool(link_status.get("ok")),
            "link_control_message": link_status.get("message", "Mininet control agent status unavailable."),
            "runtime_scale_note": model["metadata"].get("runtime_scale_note"),
        },
    }
