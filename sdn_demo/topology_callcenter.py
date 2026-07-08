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
CONTROLLER_LOG = Path(__file__).with_name("controller.log")

POLICY_TESTS = [
    ("h20", "h30", False, "Project A must not reach Project B"),
    ("h20", "h90", True, "Project A can reach Voice service"),
    ("h20", "hzalo", True, "Project A can reach Zalo simulator"),
    ("h20", "hcall", True, "Project A can reach Call App simulator"),
    ("h20", "hsocial", False, "Project A must not reach Social Media"),
    ("h50", "h60", False, "Telesale and Branch Admin are limited"),
    ("h50", "hcall", True, "Telesale can reach Call App simulator"),
    ("h50", "hsocial", False, "Telesale must not reach Social Media"),
]


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


def packet_loss_line(output):
    for line in output.splitlines():
        if "packet loss" in line:
            return line.strip()
    return "no ping summary returned"


class CallCenterCLI(CLI):
    def do_testsdn(self, line):
        "Run the expected SDN allow/deny ping test suite."
        info("\n*** Running SDN policy tests\n")
        passed = 0
        failed = 0

        for src_name, dst_name, should_pass, reason in POLICY_TESTS:
            src = self.mn.get(src_name)
            dst = self.mn.get(dst_name)
            output = src.cmd(f"ping -c 2 -W 1 {dst.IP()}")
            reachable = " 0% packet loss" in output or " 0.0% packet loss" in output
            matched = reachable == should_pass
            status = "PASS" if matched else "FAIL"
            expected = "allow" if should_pass else "deny"
            actual = "allow" if reachable else "deny"

            if matched:
                passed += 1
            else:
                failed += 1

            info(
                f"{status:4} {src_name:>4} -> {dst_name:<7} "
                f"expected={expected:<5} actual={actual:<5} "
                f"{packet_loss_line(output)} | {reason}\n"
            )

        info(f"\n*** Summary: {passed} passed, {failed} failed\n")
        if failed:
            info("*** Check controller log: sh tail -n 80 sdn_demo/controller.log\n")

    def do_sdninfo(self, line):
        "Show where the SDN demo components are running."
        info("\n*** SDN demo entry points\n")
        info("You are inside the SDN dataplane now: Mininet + Open vSwitch.\n")
        info("Switch: s1, OpenFlow 1.3, remote controller 127.0.0.1:6653\n")
        info(f"Policy file: {POLICY_FILE}\n")
        info(f"Controller log: {CONTROLLER_LOG}\n")
        info("\nUseful commands:\n")
        info("  testsdn                              run detailed allow/deny tests\n")
        info("  sh ovs-ofctl -O OpenFlow13 dump-flows s1\n")
        info("  sh tail -n 80 sdn_demo/controller.log\n")
        info("  nodes                                list simulated hosts\n")
        info("  net                                  show links\n")


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
    info("*** Run all policy tests: testsdn\n")
    info("*** Show SDN entry points: sdninfo\n")
    info("*** Test list inside Mininet: sh cat sdn_demo/test_commands.txt\n\n")

    CallCenterCLI(net)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
