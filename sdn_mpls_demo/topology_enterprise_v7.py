#!/usr/bin/env python3
"""Executable Mininet topology for the approved CCH enterprise v7 design.

Simulation boundaries:
- one controlled OVS represents each collapsed Core/Distribution HA pair;
- one nftables namespace represents the active firewall HA cluster per site;
- CE and MPLS L2VPN nodes are transparent Linux bridges, not provider PE/P MPLS;
- ipsec_l3 is routed tunnel behavior between firewall namespaces only, not
  IKE/ESP/XFRM cryptography.
"""

from __future__ import annotations

import ipaddress
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import RemoteController

try:
    from scripts.network_model import build_host_inventory, dpid_map, load_network_model, runtime_switch_name
    from sdn_mpls_demo import topology_hybrid_sdn as legacy
    from sdn_mpls_demo.firewall_nftables import apply_to_mininet, expose_named_firewall_namespaces, remove_named_firewall_namespaces
    from sdn_mpls_demo.policy_engine import PolicyEngine
    from sdn_mpls_demo.runtime_contract import source_truth_runtime_links
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.network_model import build_host_inventory, dpid_map, load_network_model, runtime_switch_name
    import topology_hybrid_sdn as legacy
    from firewall_nftables import apply_to_mininet, expose_named_firewall_namespaces, remove_named_firewall_namespaces
    from policy_engine import PolicyEngine
    from runtime_contract import source_truth_runtime_links


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
POLICY_FILE = BASE_DIR / "policy.yml"
ROUTING_FILE = ROOT_DIR / "vars" / "routing.yml"
RUNTIME_DIR = BASE_DIR / "runtime"
RUNTIME_INVENTORY_FILE = RUNTIME_DIR / "enterprise_v7_runtime.json"
NETWORK_MODEL = load_network_model()
ROUTING = yaml.safe_load(ROUTING_FILE.read_text(encoding="utf-8"))
DPIDS = dpid_map(NETWORK_MODEL)

SERVICE_NET_DPID = "00000000000000fe"
CE_DPIDS = {
    "ce_hq1": "00000000000000f1",
    "ce_hq2": "00000000000000f2",
    "ce_branch1": "00000000000000f3",
    "ce_branch2": "00000000000000f4",
}
L2VPN_DPIDS = {
    "l2vpn_primary": "00000000000000fd",
    "l2vpn_backup": "00000000000000fc",
}

PRIMARY_L2_LOGICAL_LINKS = {
    "core_hq-ce_hq1",
    "ce_hq1-l2vpn_primary",
    "l2vpn_primary-ce_branch1",
    "ce_branch1-dist_branch",
}
BACKUP_L2_LOGICAL_LINKS = {
    "core_hq-ce_hq2",
    "ce_hq2-l2vpn_backup",
    "l2vpn_backup-ce_branch2",
    "ce_branch2-dist_branch",
}
PRIMARY_L2_SEGMENTS = [
    ("core_hq", "ce_hq1"),
    ("ce_hq1", "l2vpn_primary"),
    ("l2vpn_primary", "ce_branch1"),
    ("ce_branch1", "dist_branch"),
]
BACKUP_L2_SEGMENTS = [
    ("core_hq", "ce_hq2"),
    ("ce_hq2", "l2vpn_backup"),
    ("l2vpn_backup", "ce_branch2"),
    ("ce_branch2", "dist_branch"),
]

# Reuse the mature socket control agent with the v7 composed-link map.
legacy.LOGICAL_LINK_SEGMENTS = {
    "core_hq-fw_hq": [("core_hq", "hq_l3_gateway"), ("hq_l3_gateway", "fw_hq")],
    "fw_hq-core_hq": [("fw_hq", "hq_l3_gateway"), ("hq_l3_gateway", "core_hq")],
    "fw_hq-ipsec_l3": [("fw_hq", "ipsec_l3")],
    "ipsec_l3-fw_hq": [("ipsec_l3", "fw_hq")],
    "ipsec_l3-fw_telesale": [("ipsec_l3", "fw_telesale")],
    "fw_telesale-ipsec_l3": [("fw_telesale", "ipsec_l3")],
    "fw_telesale-dist_branch": [("fw_telesale", "telesale_l3_gateway"), ("telesale_l3_gateway", "dist_branch")],
    "dist_branch-fw_telesale": [("dist_branch", "telesale_l3_gateway"), ("telesale_l3_gateway", "fw_telesale")],
    "fw_hq-internet_zone": [("fw_hq", "internet_zone")],
    "internet_zone-fw_hq": [("internet_zone", "fw_hq")],
    "fw_telesale-internet_zone": [("fw_telesale", "internet_zone")],
    "internet_zone-fw_telesale": [("internet_zone", "fw_telesale")],
}
for service_name in NETWORK_MODEL["services"]:
    legacy.LOGICAL_LINK_SEGMENTS[f"internet_zone-{service_name}"] = [("internet_zone", "service_net"), ("service_net", service_name)]
    legacy.LOGICAL_LINK_SEGMENTS[f"{service_name}-internet_zone"] = [(service_name, "service_net"), ("service_net", "internet_zone")]


def _logical_node_name(name: str) -> str:
    return runtime_switch_name(NETWORK_MODEL, name)


def load_policy() -> dict:
    engine = PolicyEngine(POLICY_FILE)
    payload = dict(engine.data)
    payload["links"] = NETWORK_MODEL["links"]
    payload["hosts"] = engine.hosts
    return payload


def add_group_hosts(net: Mininet, policy: dict, switches: dict) -> list[str]:
    created: list[str] = []
    inventory = build_host_inventory(NETWORK_MODEL)
    group_indexes: dict[str, int] = {}
    for name, endpoint in inventory.items():
        if endpoint["kind"] not in {"user", "guest", "iot"}:
            continue
        group = NETWORK_MODEL["host_groups"][endpoint["group"]]
        group_indexes[endpoint["group"]] = group_indexes.get(endpoint["group"], 0) + 1
        index = group_indexes[endpoint["group"]]
        network = ipaddress.ip_network(group["subnet"])
        host = net.addHost(
            name,
            ip=f"{endpoint['ip']}/{network.prefixlen}",
            defaultRoute=f"via {group['gateway']}",
        )
        port_prefix = str(group.get("interface_prefix", group["prefix"]))
        net.addLink(
            host,
            switches[str(endpoint["switch"])],
            intfName1=f"h{int(group['vlan'])}u{index:02d}-eth0",
            intfName2=f"{port_prefix}-u{index:02d}",
            cls=TCLink,
            bw=100,
            delay="1ms",
        )
        created.append(name)
    return created


def _add_service_hosts(net: Mininet, service_net) -> None:
    for index, name in enumerate(NETWORK_MODEL["services"], start=1):
        host = net.addHost(name, ip=None)
        net.addLink(host, service_net, intfName2=f"svc-{index:02d}", cls=TCLink, bw=100, delay="4ms")


def _add_infrastructure_hosts(net: Mininet, switches: dict) -> None:
    for index, (name, service) in enumerate(NETWORK_MODEL["infrastructure_services"].items(), start=1):
        host = net.addHost(name, ip=None)
        net.addLink(host, switches[service["switch"]], intfName2=f"inf-s{index:02d}", cls=TCLink, bw=100, delay="1ms")


def _configure_vlan_switching(switches: dict) -> None:
    inventory = build_host_inventory(NETWORK_MODEL)
    group_indexes: dict[str, int] = {}
    for endpoint in inventory.values():
        if endpoint["kind"] not in {"user", "guest", "iot"}:
            continue
        group_name = endpoint["group"]
        group = NETWORK_MODEL["host_groups"][group_name]
        group_indexes[group_name] = group_indexes.get(group_name, 0) + 1
        prefix = group.get("interface_prefix", group["prefix"])
        switches[endpoint["switch"]].cmd(
            f"ovs-vsctl set port {prefix}-u{group_indexes[group_name]:02d} tag={int(group['vlan'])}"
        )

    for index, _name in enumerate(NETWORK_MODEL["infrastructure_services"], start=1):
        switches["infra_access"].cmd(f"ovs-vsctl set port inf-s{index:02d} tag=100")

    trunks = (
        ("access_floor1", "core_hq", "f1-eth99", "core-eth01", [93, 101, 120, 140]),
        ("access_floor2", "core_hq", "f2-eth99", "core-eth02", [103, 104, 110]),
        ("infra_access", "core_hq", "inf-eth99", "core-eth04", [100]),
        ("access_branch", "dist_branch", "br-eth99", "bd-eth01", [50, 93]),
    )
    for left, right, left_port, right_port, vlans in trunks:
        allowed = ",".join(str(vlan) for vlan in vlans)
        switches[left].cmd(f"ovs-vsctl set port {left_port} vlan_mode=trunk trunks={allowed}")
        switches[right].cmd(f"ovs-vsctl set port {right_port} vlan_mode=trunk trunks={allowed}")

    # Routed gateway trunks. Branch intentionally excludes VLAN 93.
    switches["core_hq"].cmd("ovs-vsctl set port core-eth03 vlan_mode=trunk trunks=93,100,101,103,104,110,120,140")
    switches["dist_branch"].cmd("ovs-vsctl set port bd-eth02 vlan_mode=trunk trunks=50")

    # L2VPN attachment circuits. OVS access ports remove/add the customer tag.
    for port in ("core-eth93p", "core-eth93b"):
        switches["core_hq"].cmd(f"ovs-vsctl set port {port} tag=93")
    for port in ("bd-eth93p", "bd-eth93b"):
        switches["dist_branch"].cmd(f"ovs-vsctl set port {port} tag=93")


def _configure_vlan_router_interface(node, parent: str, vlan_addresses: list[tuple[int, str]]) -> None:
    node.cmd(f"ip addr flush dev {parent}")
    node.cmd(f"ip link set {parent} up")
    for vlan, address in vlan_addresses:
        interface = f"v{vlan}-{parent[-4:]}"
        node.cmd(f"ip link del {interface} 2>/dev/null || true")
        node.cmd(f"ip link add link {parent} name {interface} type vlan id {vlan}")
        node.cmd(f"ip link set {interface} up")
        node.cmd(f"ip addr add {address} dev {interface}")


def _configure_router_interface(node, interface: str, address: str) -> None:
    node.cmd(f"ip addr flush dev {interface}")
    node.cmd(f"ip link set {interface} up")
    node.cmd(f"ip addr add {address} dev {interface}")


def _link_cidr(link_name: str, endpoint: str) -> str:
    link = ROUTING["links"][link_name]
    prefix = ipaddress.ip_network(link["cidr"]).prefixlen
    return f"{link[endpoint]['ip']}/{prefix}"


def _add_route(node, prefix: str, next_hop: str) -> None:
    node.cmd(f"ip route replace {prefix} via {next_hop}")


def configure_declared_routes(net: Mininet) -> None:
    routes = ROUTING["routes"]
    hq = net.get("hq_l3_gateway")
    branch = net.get("telesale_l3_gateway")
    fw_hq = net.get("fw_hq")
    fw_br = net.get("fw_telesale")
    ipsec = net.get("ipsec_l3")

    for node, key in ((hq, "hq_l3_gateway"), (branch, "telesale_l3_gateway")):
        route_set = routes[key]
        _add_route(node, "0.0.0.0/0", route_set["default_route"]["next_hop"])
        for route in route_set.get("user_routes", []):
            _add_route(node, route["prefix"], route["next_hop"])

    for node, key in ((fw_hq, "fw_hq"), (fw_br, "fw_telesale")):
        route_set = routes[key]
        _add_route(node, "0.0.0.0/0", route_set["default_route"]["next_hop"])
        for prefix in route_set.get("inside_routes", []):
            _add_route(node, prefix, route_set["inside_next_hop"])
        for prefix in route_set.get("tunnel_routes", []):
            _add_route(node, prefix, route_set["tunnel_next_hop"])

    ipsec_routes = routes["ipsec_l3"]
    for prefix in ipsec_routes["hq_routes"]:
        _add_route(ipsec, prefix, ipsec_routes["hq_next_hop"])
    for prefix in ipsec_routes["branch_routes"]:
        _add_route(ipsec, prefix, ipsec_routes["branch_next_hop"])


def _configure_routing(net: Mininet, policy: dict) -> None:
    hq = net.get("hq_l3_gateway")
    branch = net.get("telesale_l3_gateway")
    ipsec = net.get("ipsec_l3")
    fw_hq = net.get("fw_hq")
    fw_br = net.get("fw_telesale")
    internet = net.get("internet_zone")

    _configure_vlan_router_interface(hq, "hq_l3-eth0", [
        (93, "10.10.93.1/24"), (100, "10.10.100.1/24"), (101, "10.10.101.1/24"),
        (103, "10.10.103.1/24"), (104, "10.10.104.1/24"), (110, "10.10.110.1/24"),
        (120, "10.10.120.1/24"), (140, "10.10.140.1/24"),
    ])
    _configure_vlan_router_interface(branch, "tele_l3-eth0", [(50, "10.20.50.1/24")])

    _configure_router_interface(hq, "hq_l3-eth1", _link_cidr("hq_l3_to_fw_hq", "endpoint_a"))
    _configure_router_interface(fw_hq, "fw_hq-eth0", _link_cidr("hq_l3_to_fw_hq", "endpoint_b"))
    _configure_router_interface(fw_hq, "fw_hq-eth2", _link_cidr("fw_hq_to_ipsec", "endpoint_a"))
    _configure_router_interface(ipsec, "ipsec-hq", _link_cidr("fw_hq_to_ipsec", "endpoint_b"))
    _configure_router_interface(ipsec, "ipsec-br", _link_cidr("ipsec_to_fw_branch", "endpoint_a"))
    _configure_router_interface(fw_br, "fw_tel-eth2", _link_cidr("ipsec_to_fw_branch", "endpoint_b"))
    _configure_router_interface(branch, "tele_l3-eth1", _link_cidr("branch_l3_to_fw_branch", "endpoint_a"))
    _configure_router_interface(fw_br, "fw_tel-eth0", _link_cidr("branch_l3_to_fw_branch", "endpoint_b"))
    _configure_router_interface(fw_hq, "fw_hq-eth1", _link_cidr("fw_hq_to_internet_zone", "endpoint_a"))
    _configure_router_interface(internet, "inet-eth0", _link_cidr("fw_hq_to_internet_zone", "endpoint_b"))
    _configure_router_interface(fw_br, "fw_tel-eth1", _link_cidr("fw_branch_to_internet_zone", "endpoint_a"))
    _configure_router_interface(internet, "inet-eth1", _link_cidr("fw_branch_to_internet_zone", "endpoint_b"))
    _configure_router_interface(internet, "inet-eth2", "10.255.30.1/24")

    configure_declared_routes(net)

    # The Internet/Partner service zone returns traffic through each local firewall.
    for prefix in ROUTING["routes"]["fw_hq"]["inside_routes"]:
        _add_route(internet, prefix, "10.255.10.1")
    for prefix in ROUTING["routes"]["fw_telesale"]["inside_routes"]:
        _add_route(internet, prefix, "10.255.10.5")

    for name, service in policy["services"].items():
        host = net.get(name)
        interface = str(host.defaultIntf())
        host.cmd(f"ip addr flush dev {interface}")
        host.cmd(f"ip addr add {service['ip']}/32 dev {interface}")
        host.cmd(f"ip addr add {service['interface_cidr']} dev {interface}")
        _add_route(host, "0.0.0.0/0", service["gateway"])
        internet.cmd(f"ip route replace {service['ip']}/32 dev inet-eth2")

    for name, service in policy["infrastructure_services"].items():
        host = net.get(name)
        interface = str(host.defaultIntf())
        host.cmd(f"ip addr flush dev {interface}")
        host.cmd(f"ip addr add {service['ip']}/24 dev {interface}")
        _add_route(host, "0.0.0.0/0", service["gateway"])


def _start_service_simulators(net: Mininet) -> None:
    for index, name in enumerate(NETWORK_MODEL["services"], start=1):
        net.get(name).cmd(
            f"cd /tmp && printf 'CCH v7 service simulator: {name}\\n' > {name}.txt; "
            f"python3 -m http.server {8000 + index} > /tmp/{name}_http.log 2>&1 &"
        )
    for index, name in enumerate(NETWORK_MODEL["infrastructure_services"], start=1):
        net.get(name).cmd(
            f"cd /tmp && printf 'CCH v7 infrastructure simulator: {name}\\n' > {name}.txt; "
            f"python3 -m http.server {9000 + index} > /tmp/{name}_http.log 2>&1 &"
        )
        if name == "hdhcp":
            dhcp_conf = (
                "interface=hdhcp-eth0\n"
                "bind-interfaces\n"
                "dhcp-range=10.10.101.150,10.10.101.199,255.255.255.0,12h\n"
                "dhcp-range=10.10.120.150,10.10.120.199,255.255.255.0,12h\n"
                "dhcp-range=10.10.103.150,10.10.103.199,255.255.255.0,12h\n"
                "dhcp-range=10.10.104.150,10.10.104.199,255.255.255.0,12h\n"
                "dhcp-range=10.10.93.150,10.10.93.199,255.255.255.0,12h\n"
                "dhcp-option=3,10.10.101.1\n"
                "dhcp-option=6,10.10.100.11\n"
                "log-dhcp\n"
                "log-facility=/tmp/dnsmasq.log\n"
            )
            net.get(name).cmd(
                f"cat << 'EOF' > /tmp/dnsmasq.conf\n{dhcp_conf}EOF\n"
                "killall dnsmasq 2>/dev/null || true\n"
                "dnsmasq -C /tmp/dnsmasq.conf &\n"
            )


def _set_segments(net: Mininet, segments: list[tuple[str, str]], state: str) -> None:
    for left, right in segments:
        net.configLinkStatus(_logical_node_name(left), _logical_node_name(right), state)


class EnterpriseV7ControlAgent(legacy.MininetControlAgent):
    """Add loop-safe VLAN 93 primary/backup switching to the existing agent."""

    def _set_link(self, link_id: str, state: str) -> dict:
        if link_id in PRIMARY_L2_LOGICAL_LINKS:
            if state == "down":
                _set_segments(self.net, PRIMARY_L2_SEGMENTS, "down")
                _set_segments(self.net, BACKUP_L2_SEGMENTS, "up")
                for item in PRIMARY_L2_LOGICAL_LINKS:
                    self.link_state[item] = "down"
                for item in BACKUP_L2_LOGICAL_LINKS:
                    self.link_state[item] = "up"
                return {"ok": True, "available": True, "message": "VLAN 93 failed over to backup L2VPN path.", "link_id": link_id, "status": "down", "links": self._link_status()["links"]}
            _set_segments(self.net, PRIMARY_L2_SEGMENTS, "up")
            _set_segments(self.net, BACKUP_L2_SEGMENTS, "down")
            for item in PRIMARY_L2_LOGICAL_LINKS:
                self.link_state[item] = "up"
            for item in BACKUP_L2_LOGICAL_LINKS:
                self.link_state[item] = "down"
            return {"ok": True, "available": True, "message": "VLAN 93 restored to primary L2VPN path.", "link_id": link_id, "status": "up", "links": self._link_status()["links"]}

        segments = self._segments_for_link(link_id)
        if not segments:
            return {"ok": False, "available": True, "message": f"No runtime mapping for {link_id}.", "link_id": link_id}
        changed = []
        for left, right in segments:
            self.net.configLinkStatus(_logical_node_name(left), _logical_node_name(right), state)
            changed.append({"left": left, "right": right, "state": state})
        if state == "up" and ("ipsec_l3" in link_id or "fw_" in link_id):
            configure_declared_routes(self.net)
        self.link_state[link_id] = state
        return {"ok": True, "available": True, "message": f"Set {link_id} {state}.", "link_id": link_id, "status": state, "changed": changed, "links": self._link_status()["links"]}


def _write_inventory(net: Mininet, duration: float) -> None:
    inventory = build_host_inventory(NETWORK_MODEL)
    payload = {
        "schema": "enterprise-v7",
        "build_duration_seconds": round(duration, 3),
        "user_count": sum(item["kind"] == "user" for item in inventory.values()),
        "endpoint_count": len(inventory),
        "controlled_ovs": list(DPIDS),
        "controlled_ovs_count": len(DPIDS),
        "firewall_namespaces": ["fw_hq", "fw_telesale"],
        "ce_bridges": list(CE_DPIDS),
        "l2vpn_bridges": list(L2VPN_DPIDS),
        "ipsec_runtime": {"node": "ipsec_l3", "path": ["fw_hq", "ipsec_l3", "fw_telesale"], "mode": "routed_tunnel_abstraction", "cryptographic_ipsec": False},
        "vlan93": {"gateway": "10.10.93.1", "gateway_site": "hq", "active_path": "primary", "backup_state": "standby"},
        "runtime_scale_note": NETWORK_MODEL["metadata"]["runtime_scale_note"],
        "mininet_nodes": sorted(net.nameToNode),
    }
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_INVENTORY_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class EnterpriseV7CLI(CLI):
    def do_v7status(self, _line):
        info("\nCCH Enterprise v7\n")
        info("  VLAN 93 gateway: HQ 10.10.93.1\n")
        info("  L2VPN: primary active, backup standby\n")
        info("  Routed intersite: Firewall HQ -> ipsec_l3 -> Firewall Branch abstraction\n")
        info("  Partner CRM/PBX: outside internal server farm\n")

    def do_firewallrules(self, _line):
        for name in ("fw_hq", "fw_telesale"):
            info(f"\n--- {name} ---\n")
            info(self.mn.get(name).cmd("nft -a list table inet cch_filter"))


def _preflight_cleanup() -> None:
    """Safely tear down any leftover virtual interfaces and bridges from previous runs."""
    try:
        subprocess.run(["mn", "-c"], capture_output=True)
    except Exception:
        pass

    try:
        res = subprocess.run(["ip", "-o", "link", "show"], capture_output=True, text=True)
        protected = {"lo", "eth0", "ens33", "ens32", "ens160"}
        for line in res.stdout.splitlines():
            parts = line.split(":")
            if len(parts) >= 2:
                name = parts[1].strip().split("@")[0]
                if name not in protected and not name.startswith("ens") and not name.startswith("docker"):
                    if any(prefix in name for prefix in [
                        "svc-", "inf-", "core-", "bd-", "f1-", "f2-", "br-", "inet-",
                        "h101", "h93", "h103", "h104", "h110", "iot", "guest",
                        "fw_", "tele_", "hq_", "ipsec", "ceh", "ceb", "v93-", "v100-",
                        "v101-", "v103-", "v104-", "v110-", "v120-", "v140-", "v50-"
                    ]):
                        subprocess.run(["ip", "link", "del", name], capture_output=True)
    except Exception:
        pass

    stale_bridges = [
        "service_net", "ce_hq1", "ce_hq2", "ce_branch1", "ce_branch2",
        "l2vpn_primary", "l2vpn_backup", "access_floor1", "access_floor2",
        "core_hq", "access_branch", "dist_branch", "infra_access"
    ]
    for br in stale_bridges:
        subprocess.run(["ovs-vsctl", "--if-exists", "del-br", br], capture_output=True)
        subprocess.run(["ip", "link", "del", br], capture_output=True)


def build_topology() -> None:
    _preflight_cleanup()
    started = time.monotonic()
    policy = load_policy()
    net = Mininet(controller=None, switch=legacy.ReliableOVSKernelSwitch, link=TCLink, autoSetMacs=True, build=False, waitConnected=True)
    controller = net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
    switches = {
        name: net.addSwitch(_logical_node_name(name), dpid=dpid, protocols="OpenFlow13", failMode="secure")
        for name, dpid in DPIDS.items()
    }
    service_net = net.addSwitch("service_net", cls=legacy.LinuxBridgeSwitch, dpid=SERVICE_NET_DPID)
    ce_nodes = {name: net.addSwitch(name, cls=legacy.LinuxBridgeSwitch, dpid=dpid) for name, dpid in CE_DPIDS.items()}
    l2vpn_nodes = {name: net.addSwitch(name, cls=legacy.LinuxBridgeSwitch, dpid=dpid) for name, dpid in L2VPN_DPIDS.items()}
    hq_l3 = net.addHost("hq_l3_gateway", cls=legacy.LinuxRouter, ip=None)
    branch_l3 = net.addHost("telesale_l3_gateway", cls=legacy.LinuxRouter, ip=None)
    ipsec_l3 = net.addHost("ipsec_l3", cls=legacy.LinuxRouter, ip=None)
    fw_hq = net.addHost("fw_hq", cls=legacy.LinuxRouter, ip=None)
    fw_br = net.addHost("fw_telesale", cls=legacy.LinuxRouter, ip=None)
    internet_zone = net.addHost("internet_zone", cls=legacy.LinuxRouter, ip=None)

    group_hosts = add_group_hosts(net, policy, switches)
    _add_service_hosts(net, service_net)
    _add_infrastructure_hosts(net, switches)

    runtime_nodes = {
        **switches,
        **ce_nodes,
        **l2vpn_nodes,
        "hq_l3_gateway": hq_l3,
        "telesale_l3_gateway": branch_l3,
        "ipsec_l3": ipsec_l3,
        "fw_hq": fw_hq,
        "fw_telesale": fw_br,
        "internet_zone": internet_zone,
    }
    for left, right, intf_left, intf_right, bw, delay in source_truth_runtime_links(NETWORK_MODEL):
        net.addLink(runtime_nodes[left], runtime_nodes[right], intfName1=intf_left, intfName2=intf_right, cls=TCLink, bw=bw, delay=delay)
    net.addLink(internet_zone, service_net, intfName1="inet-eth2", intfName2="svc-zone", cls=TCLink, bw=1000, delay="1ms")

    info("*** Starting CCH enterprise v7 topology\n")
    net.build()
    controller.start()
    for switch in switches.values():
        switch.start([controller])
        switch.cmd(f"ovs-vsctl set controller {switch.name} inactivity_probe=60000")
    net.waitConnected(timeout=15)
    service_net.start([])
    for node in ce_nodes.values():
        node.start([])
    for node in l2vpn_nodes.values():
        node.start([])
    _configure_vlan_switching(switches)
    _set_segments(net, BACKUP_L2_SEGMENTS, "up")

    control_agent = None
    try:
        _configure_routing(net, policy)
        expose_named_firewall_namespaces(net)
        firewall_status = apply_to_mininet(net)
        _start_service_simulators(net)
        control_agent = EnterpriseV7ControlAgent(net, policy)
        for item in PRIMARY_L2_LOGICAL_LINKS:
            control_agent.link_state[item] = "up"
        for item in BACKUP_L2_LOGICAL_LINKS:
            control_agent.link_state[item] = "down"
        control_agent.start()
        duration = time.monotonic() - started
        _write_inventory(net, duration)
        info(f"*** Ready: {len(group_hosts)} runtime user/enterprise endpoints; {len(DPIDS)} controlled OVS\n")
        info("*** VLAN 93: Primary L2VPN active; Backup standby; gateway 10.10.93.1 only at HQ\n")
        info("*** Routed intersite: firewall-to-firewall ipsec_l3 behavior abstraction; no cryptographic IPsec claim\n")
        info("*** Firewall: one nftables namespace per HA pair abstraction\n")
        info("*** nftables: " + ", ".join(f"{name}={item['rule_count']} rules" for name, item in firewall_status.items()) + "\n")
        if os.environ.get("CCH_DAEMON") == "1" or not sys.stdin.isatty():
            info("*** Running in daemon mode (non-interactive)...\n")
            while True:
                time.sleep(3600)
        else:
            EnterpriseV7CLI(net)
    finally:
        if control_agent is not None:
            control_agent.stop()
        remove_named_firewall_namespaces()
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
