#!/usr/bin/env python3
"""Topology 100 user cho Hybrid MPLS L3VPN + SDN Edge Policy."""

from __future__ import annotations

import ipaddress
from pathlib import Path

import yaml
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Node, OVSBridge, OVSKernelSwitch, RemoteController


BASE_DIR = Path(__file__).resolve().parent
POLICY_FILE = BASE_DIR / "policy.yml"

DPIDS = {
    "access_hq_a": "0000000000000001",
    "access_hq_b": "0000000000000002",
    "access_hq_c": "0000000000000003",
    "voice_mgmt": "0000000000000004",
    "core_hq": "0000000000000005",
    "access_branch": "0000000000000006",
    "dist_branch": "0000000000000007",
}


class LinuxRouter(Node):
    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1 >/dev/null")
        self.cmd("sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null")
        self.cmd("sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0 >/dev/null")
        super().terminate()


def load_policy():
    return yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))


def add_group_hosts(net, policy, switches):
    created = []
    for group_name, group in policy["host_groups"].items():
        network = ipaddress.ip_network(group["subnet"])
        gateway = str(network.network_address + 1)
        first_host = int(group.get("first_host", 11))
        for index in range(1, int(group["count"]) + 1):
            host_name = f"{group['prefix']}_{index:02d}"
            address = str(network.network_address + first_host + index - 1)
            host = net.addHost(
                host_name,
                ip=f"{address}/{network.prefixlen}",
                defaultRoute=f"via {gateway}",
            )
            net.addLink(
                host,
                switches[group["switch"]],
                cls=TCLink,
                bw=100,
                delay="1ms",
            )
            created.append(host_name)
    return created


def add_route(node, prefix, next_hop):
    node.cmd(f"ip route replace {prefix} via {next_hop}")


def configure_router_interface(node, interface, addresses):
    node.cmd(f"ip addr flush dev {interface}")
    node.cmd(f"ip link set {interface} up")
    for address in addresses:
        node.cmd(f"ip addr add {address} dev {interface}")


def configure_routing(net, policy):
    ce_hq = net.get("ce_hq")
    ce_branch = net.get("ce_branch")
    fw_hq = net.get("fw_hq")
    fw_branch = net.get("fw_branch")

    configure_router_interface(
        ce_hq,
        "ce_hq-eth0",
        ["172.16.20.1/24", "172.16.30.1/24", "172.16.40.1/24", "172.16.90.1/24", "10.255.20.1/30"],
    )
    configure_router_interface(ce_hq, "ce_hq-eth1", ["10.255.10.1/29"])
    configure_router_interface(
        ce_branch,
        "ce_branch-eth0",
        ["172.16.50.1/24", "172.16.60.1/24", "10.255.21.1/30"],
    )
    configure_router_interface(ce_branch, "ce_branch-eth1", ["10.255.10.2/29"])

    configure_router_interface(fw_hq, "fw_hq-eth0", ["10.255.20.2/30"])
    configure_router_interface(fw_hq, "fw_hq-eth1", ["10.255.30.1/24"])
    configure_router_interface(fw_branch, "fw_branch-eth0", ["10.255.21.2/30"])
    configure_router_interface(fw_branch, "fw_branch-eth1", ["10.255.30.2/24"])

    for prefix in ("172.16.50.0/24", "172.16.60.0/24"):
        add_route(ce_hq, prefix, "10.255.10.2")
    for prefix in ("172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.90.0/24"):
        add_route(ce_branch, prefix, "10.255.10.1")
    add_route(ce_hq, "172.16.200.0/22", "10.255.20.2")
    add_route(ce_branch, "172.16.200.0/22", "10.255.21.2")

    for prefix in ("172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.90.0/24"):
        add_route(fw_hq, prefix, "10.255.20.1")
    for prefix in ("172.16.50.0/24", "172.16.60.0/24"):
        add_route(fw_branch, prefix, "10.255.21.1")

    service_transit = {
        name: service["transit_ip"]
        for name, service in policy["services"].items()
        if "transit_ip" in service
    }
    for name, transit_ip in service_transit.items():
        service = policy["services"][name]
        host = net.get(name)
        interface = str(host.defaultIntf())
        host.cmd(f"ip addr flush dev {interface}")
        host.cmd(f"ip addr add {service['ip']}/32 dev {interface}")
        host.cmd(f"ip addr add {transit_ip}/24 dev {interface}")
        for prefix in ("172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.90.0/24"):
            add_route(host, prefix, "10.255.30.1")
        for prefix in ("172.16.50.0/24", "172.16.60.0/24"):
            add_route(host, prefix, "10.255.30.2")
        add_route(fw_hq, f"{service['ip']}/32", transit_ip)
        add_route(fw_branch, f"{service['ip']}/32", transit_ip)


def start_service_simulators(net):
    for name in ("hzalo", "hcall", "hsocial", "hinternet"):
        host = net.get(name)
        host.cmd(f"printf 'Dịch vụ mô phỏng: {name}\\n' > /tmp/{name}.txt")
        host.cmd(
            f"cd /tmp && python3 -m http.server 8000 "
            f">/tmp/{name}_http.log 2>&1 &"
        )


def build_topology():
    policy = load_policy()
    net = Mininet(
        controller=None,
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=True,
        build=False,
        waitConnected=True,
    )
    controller = net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653,
    )

    switches = {
        name: net.addSwitch(
            name,
            dpid=dpid,
            protocols="OpenFlow13",
            failMode="secure",
        )
        for name, dpid in DPIDS.items()
    }
    mpls_cloud = net.addSwitch("mpls_cloud", cls=OVSBridge, failMode="standalone")
    internet = net.addSwitch("internet", cls=OVSBridge, failMode="standalone")

    user_hosts = add_group_hosts(net, policy, switches)
    h90 = net.addHost("h90", ip="172.16.90.10/24", defaultRoute="via 172.16.90.1")
    net.addLink(h90, switches["voice_mgmt"], cls=TCLink, bw=50, delay="2ms")

    services = {}
    for service_name in ("hzalo", "hcall", "hsocial", "hinternet"):
        services[service_name] = net.addHost(service_name, ip=None)
        net.addLink(services[service_name], internet, cls=TCLink, bw=100, delay="4ms")

    ce_hq = net.addHost("ce_hq", cls=LinuxRouter, ip=None)
    ce_branch = net.addHost("ce_branch", cls=LinuxRouter, ip=None)
    fw_hq = net.addHost("fw_hq", cls=LinuxRouter, ip=None)
    fw_branch = net.addHost("fw_branch", cls=LinuxRouter, ip=None)

    net.addLink(switches["access_hq_a"], switches["core_hq"], cls=TCLink, bw=1000, delay="1ms")
    net.addLink(switches["access_hq_b"], switches["core_hq"], cls=TCLink, bw=1000, delay="1ms")
    net.addLink(switches["access_hq_c"], switches["core_hq"], cls=TCLink, bw=1000, delay="1ms")
    net.addLink(switches["voice_mgmt"], switches["core_hq"], cls=TCLink, bw=500, delay="1ms")
    net.addLink(switches["access_branch"], switches["dist_branch"], cls=TCLink, bw=1000, delay="1ms")

    net.addLink(switches["core_hq"], ce_hq, intfName2="ce_hq-eth0", cls=TCLink, bw=200, delay="2ms")
    net.addLink(ce_hq, mpls_cloud, intfName1="ce_hq-eth1", cls=TCLink, bw=100, delay="10ms")
    net.addLink(ce_branch, mpls_cloud, intfName1="ce_branch-eth1", cls=TCLink, bw=100, delay="10ms")
    net.addLink(switches["dist_branch"], ce_branch, intfName2="ce_branch-eth0", cls=TCLink, bw=200, delay="2ms")

    net.addLink(switches["core_hq"], fw_hq, intfName2="fw_hq-eth0", cls=TCLink, bw=200, delay="2ms")
    net.addLink(fw_hq, internet, intfName1="fw_hq-eth1", cls=TCLink, bw=100, delay="5ms")
    net.addLink(switches["dist_branch"], fw_branch, intfName2="fw_branch-eth0", cls=TCLink, bw=200, delay="2ms")
    net.addLink(fw_branch, internet, intfName1="fw_branch-eth1", cls=TCLink, bw=100, delay="5ms")

    info("*** Khởi động topology Hybrid MPLS L3VPN + SDN Edge Policy\n")
    net.build()
    controller.start()
    for switch in switches.values():
        switch.start([controller])
    mpls_cloud.start([])
    internet.start([])

    configure_routing(net, policy)
    start_service_simulators(net)

    info(f"*** Đã tạo {len(user_hosts)} user và 5 service.\n")
    info("*** Controller chỉ quản lý 7 OVS; CE, Firewall và MPLS Cloud không dùng OpenFlow.\n")
    info("*** Thử: h20_01 ping -c 2 h30_01 (bị chặn)\n")
    info("*** Thử: h20_01 ping -c 2 h90 (cho phép)\n")
    info("*** Thử: h50_01 ping -c 2 h20_01 (liên site qua MPLS logic)\n")
    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
