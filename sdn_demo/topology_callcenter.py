#!/usr/bin/env python3
"""Mininet topology for the Call Center BPO SDN policy demo.

The topology intentionally uses one central Open vSwitch so the demo can run on
a small Ubuntu VM. It simulates SDN policy enforcement, not MPLS L3VPN behavior.
"""

from pathlib import Path

import yaml
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


POLICY_FILE = Path(__file__).with_name("policy.yml")


def load_policy():
    with POLICY_FILE.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def configure_host(host, host_data, gateway_mac):
    intf = host.defaultIntf()
    gateway_ip = host_data["gateway"]
    host.cmd(f"ip route replace default via {gateway_ip} dev {intf}")
    host.cmd(f"ip neigh replace {gateway_ip} lladdr {gateway_mac} dev {intf} nud permanent")
    host.cmd("sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null")
    host.cmd("sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null")


def start_service_simulators(net):
    services = {
        "hzalo": "Zalo service simulator",
        "hcall": "Call App service simulator",
        "hsocial": "Social Media service simulator",
    }
    for host_name, label in services.items():
        host = net.get(host_name)
        host.cmd(f"echo '{label}' > /tmp/index.html")
        host.cmd("cd /tmp && python3 -m http.server 8000 >/tmp/http_server.log 2>&1 &")


def build_topology():
    policy = load_policy()
    gateway_mac = policy["gateway"]["mac"]

    net = Mininet(
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=False,
        build=False,
    )

    info("*** Adding remote controller 127.0.0.1:6653\n")
    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653,
    )

    info("*** Adding central Open vSwitch s1-core with OpenFlow 1.3\n")
    switch = net.addSwitch(
        "s1",
        dpid="0000000000000001",
        protocols="OpenFlow13",
        failMode="secure",
    )

    info("*** Adding hosts\n")
    for host_name, host_data in policy["hosts"].items():
        host = net.addHost(
            host_name,
            ip=host_data["cidr"],
            mac=host_data["mac"],
            defaultRoute=None,
        )
        net.addLink(
            switch,
            host,
            port1=int(host_data["switch_port"]),
            cls=TCLink,
            bw=100,
        )

    info("*** Starting network\n")
    net.build()
    net.start()

    info("*** Configuring host default routes and static gateway ARP\n")
    for host_name, host_data in policy["hosts"].items():
        configure_host(net.get(host_name), host_data, gateway_mac)

    start_service_simulators(net)

    info("\n*** SDN Call Center BPO demo is ready\n")
    info("*** Try: h20 ping -c 2 h90\n")
    info("*** Try: h20 ping -c 2 h30\n")
    info("*** Test list inside Mininet: sh cat sdn_demo/test_commands.txt\n\n")

    CLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
