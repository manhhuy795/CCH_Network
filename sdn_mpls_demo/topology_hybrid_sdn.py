#!/usr/bin/env python3
"""Topology 110 user cho Hybrid MPLS L3VPN + SDN Edge Policy."""

from __future__ import annotations

import ipaddress
import os
import re
import unicodedata
from pathlib import Path

import yaml
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Node, OVSBridge, OVSKernelSwitch, RemoteController

try:
    from scripts.network_model import dpid_map, load_network_model
    from sdn_mpls_demo.policy_engine import PolicyEngine
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.network_model import dpid_map, load_network_model
    from policy_engine import PolicyEngine


BASE_DIR = Path(__file__).resolve().parent
POLICY_FILE = BASE_DIR / "policy.yml"

DPIDS = dpid_map(load_network_model())


class LinuxRouter(Node):
    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1 >/dev/null")
        self.cmd("sysctl -w net.ipv4.conf.all.rp_filter=0 >/dev/null")
        self.cmd("sysctl -w net.ipv4.conf.default.rp_filter=0 >/dev/null")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0 >/dev/null")
        super().terminate()


POLICY_TESTS = (
    ("Project isolation", "h20_01", "h30_01", False, "Project A cannot ping Project B"),
    ("Project isolation", "h20_01", "h40_01", False, "Project A cannot ping Project C"),
    ("Project isolation", "h30_01", "h20_01", False, "Project B cannot ping Project A"),
    ("Project isolation", "h30_01", "h40_01", False, "Project B cannot ping Project C"),
    ("Project isolation", "h40_01", "h20_01", False, "Project C cannot ping Project A"),
    ("Project isolation", "h40_01", "h30_01", False, "Project C cannot ping Project B"),
    ("Branch isolation", "h50_01", "h60_01", False, "Telesale cannot ping BackOffice"),
    ("Branch isolation", "h60_01", "h50_01", False, "BackOffice cannot ping Telesale"),
    ("Voice", "h20_01", "h90", True, "Project A can reach Voice Service"),
    ("Voice", "h30_01", "h90", True, "Project B can reach Voice Service"),
    ("Voice", "h40_01", "h90", True, "Project C can reach Voice Service"),
    ("Voice", "h50_01", "h90", True, "Telesale can reach Voice via MPLS"),
    ("Voice", "h60_01", "h90", True, "BackOffice can reach Voice via MPLS"),
    ("Voice", "h70_01", "h90", True, "IT Support can reach Voice"),
    ("Internet services", "h20_01", "hzalo", True, "Project A can use Zalo via Firewall HQ"),
    ("Internet services", "h20_01", "hcall", True, "Project A can use Call App via Firewall HQ"),
    ("Internet services", "h20_01", "hinternet", True, "Project A can use Internet test via Firewall HQ"),
    ("Internet services", "h50_01", "hzalo", True, "Telesale can use Zalo via Firewall Branch"),
    ("Internet services", "h50_01", "hcall", True, "Telesale can use Call App via Firewall Branch"),
    ("Internet services", "h60_01", "hinternet", True, "BackOffice can use Internet test via Firewall Branch"),
    ("Social block", "h20_01", "hsocial", False, "Project A is blocked from Social Media at HQ Core SDN"),
    ("Social block", "h30_01", "hsocial", False, "Project B is blocked from Social Media at HQ Core SDN"),
    ("Social block", "h40_01", "hsocial", False, "Project C is blocked from Social Media at HQ Core SDN"),
    ("Social block", "h50_01", "hsocial", False, "Telesale is blocked from Social Media at Branch Distribution SDN"),
    ("Social block", "h60_01", "hsocial", False, "BackOffice is blocked from Social Media at Branch Distribution SDN"),
    ("Controlled intersite", "h50_01", "h20_01", False, "Telesale cannot ping Project A; only IT has support access"),
    ("Controlled intersite", "h20_01", "h50_01", False, "Project A cannot ping Telesale; only IT has support access"),
    ("Controlled intersite", "h60_01", "h20_01", False, "BackOffice has no lateral access to Project A"),
    ("Controlled intersite", "h20_01", "h60_01", False, "Project A has no lateral access to BackOffice"),
    ("IT support", "h70_01", "h20_01", True, "IT Support can remote/support Project A"),
    ("IT support", "h70_01", "h30_01", True, "IT Support can remote/support Project B"),
    ("IT support", "h70_01", "h50_01", True, "IT Support can remote/support Telesale via MPLS"),
    ("IT support", "h70_01", "hsocial", True, "IT Support can test declared services"),
    ("Internet inbound", "hinternet", "h20_01", False, "Internet cannot initiate ping to Project A"),
    ("Internet inbound", "hzalo", "h30_01", False, "Zalo simulator cannot initiate ping to Project B"),
    ("Internet inbound", "hcall", "h50_01", False, "Call App simulator cannot initiate ping to Telesale"),
    ("Internet inbound", "hsocial", "h60_01", False, "Social simulator cannot initiate ping to BackOffice"),
    ("Internet inbound", "hinternet", "h70_01", False, "Internet cannot initiate ping to IT"),
)

def endpoint_ip(net, policy, host_name):
    service = policy.get("services", {}).get(host_name)
    return service["ip"] if service else net.get(host_name).IP()


def ping_reachable(net, policy, source_name, destination_name, count=2, timeout=1):
    source = net.get(source_name)
    destination_ip = endpoint_ip(net, policy, destination_name)
    output = source.cmd(f"ping -c {count} -i 0.2 -W {timeout} {destination_ip}")
    loss = re.search(r"([0-9.]+)% packet loss", output)
    reachable = bool(loss and float(loss.group(1)) < 100)
    return reachable, output


def emit(message=""):
    print(message, flush=True)


def ascii_text(value):
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())


def short_text(value, width):
    value = ascii_text(value)
    value = str(value)
    return value if len(value) <= width else value[: width - 3] + "..."


def run_policy_tests(net, policy, title="Kiá»ƒm tra policy báº±ng ping tháº­t"):
    width = 112
    emit()
    emit("=" * width)
    emit(short_text(title, width))
    emit("PASS = real ping matches policy. FAIL = check controller.log / dump-flows.")
    emit("=" * width)
    emit(
        f"{'NO':<3} {'POLICY GROUP':<19} {'SOURCE':<10} {'DEST':<10} "
        f"{'EXPECT':<6} {'PING':<6} {'RESULT':<6} NOTE"
    )
    emit("-" * width)
    passed = 0
    for index, (category, source_name, destination_name, expected, reason) in enumerate(POLICY_TESTS, start=1):
        reachable, _output = ping_reachable(net, policy, source_name, destination_name)
        matched = reachable == expected
        passed += int(matched)
        emit(
            f"{index:<3} {short_text(category, 19):<19} {source_name:<10} {destination_name:<10} "
            f"{'ALLOW' if expected else 'DENY':<6} {'ALLOW' if reachable else 'DENY':<6} "
            f"{'PASS' if matched else 'FAIL':<6} {short_text(reason, 42)}"
        )
    emit("-" * width)
    emit(f"KET QUA: {passed}/{len(POLICY_TESTS)} policy test dat")
    if passed != len(POLICY_TESTS):
        emit("CANH BAO: Co test FAIL. Hay xem sdn_mpls_demo/runtime/controller.log va ovs dump-flows de debug.")
    emit("=" * width)
    emit()


class CallCenterCLI(CLI):
    def __init__(self, net, policy):
        self.policy = policy
        super().__init__(net)

    def service_ip(self, host_name):
        return endpoint_ip(self.mn, self.policy, host_name)

    def do_testpolicy(self, _line):
        "Cháº¡y ma tráº­n ping chi tiáº¿t theo policy ALLOW/DENY."
        run_policy_tests(self.mn, self.policy, title="Kiá»ƒm tra policy thá»§ cĂ´ng báº±ng ping tháº­t")

    def do_isolationflows(self, _line):
        "Hiá»ƒn thá»‹ cĂ¡c flow DROP priority 400 trĂªn OVS."
        info("\n*** Isolation flow priority 400\n")
        for switch_name in DPIDS:
            switch = self.mn.get(switch_name)
            info(f"\n--- {switch_name} ---\n")
            info(switch.cmd(
                f"ovs-ofctl -O OpenFlow13 dump-flows {switch_name} "
                f"| grep 'priority=400' || true"
            ))


def load_policy():
    return PolicyEngine(POLICY_FILE).data


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
                intfName2=f"{group['prefix']}-u{index:02d}",
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
        [
            "172.16.20.1/24",
            "172.16.30.1/24",
            "172.16.40.1/24",
            "172.16.70.1/24",
            "172.16.90.1/24",
            "10.255.20.1/30",
        ],
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
    for prefix in ("172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.70.0/24", "172.16.90.0/24"):
        add_route(ce_branch, prefix, "10.255.10.1")
    add_route(ce_hq, "172.16.200.0/22", "10.255.20.2")
    add_route(ce_branch, "172.16.200.0/22", "10.255.21.2")

    for prefix in ("172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.70.0/24", "172.16.90.0/24"):
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
        for prefix in ("172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.70.0/24", "172.16.90.0/24"):
            add_route(host, prefix, "10.255.30.1")
        for prefix in ("172.16.50.0/24", "172.16.60.0/24"):
            add_route(host, prefix, "10.255.30.2")
        add_route(fw_hq, f"{service['ip']}/32", transit_ip)
        add_route(fw_branch, f"{service['ip']}/32", transit_ip)


def start_service_simulators(net):
    for name in ("hzalo", "hcall", "hsocial", "hinternet"):
        host = net.get(name)
        host.cmd(f"printf 'Dá»‹ch vá»¥ mĂ´ phá»ng: {name}\\n' > /tmp/{name}.txt")
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
    # Mininet chá»‰ tá»± sinh DPID cho tĂªn canonical nhÆ° s1/s23. Hai bridge
    # standalone váº«n cáº§n DPID tÆ°á»ng minh dĂ¹ khĂ´ng káº¿t ná»‘i SDN Controller.
    mpls_cloud = net.addSwitch(
        "mpls_cloud",
        cls=OVSBridge,
        dpid="00000000000000f1",
        failMode="standalone",
    )
    internet = net.addSwitch(
        "internet",
        cls=OVSBridge,
        dpid="00000000000000f2",
        failMode="standalone",
    )

    user_hosts = add_group_hosts(net, policy, switches)
    voice_service = policy["services"]["h90"]
    voice_prefix = ipaddress.ip_network(voice_service["subnet"]).prefixlen
    h90 = net.addHost(
        "h90",
        ip=f"{voice_service['ip']}/{voice_prefix}",
        defaultRoute=f"via {voice_service['gateway']}",
    )
    net.addLink(
        h90,
        switches["voice_access"],
        intfName2="voice-eth01",
        cls=TCLink,
        bw=50,
        delay="2ms",
    )

    services = {}
    for service_name in ("hzalo", "hcall", "hsocial", "hinternet"):
        services[service_name] = net.addHost(service_name, ip=None)
        net.addLink(services[service_name], internet, cls=TCLink, bw=100, delay="4ms")

    ce_hq = net.addHost("ce_hq", cls=LinuxRouter, ip=None)
    ce_branch = net.addHost("ce_branch", cls=LinuxRouter, ip=None)
    fw_hq = net.addHost("fw_hq", cls=LinuxRouter, ip=None)
    fw_branch = net.addHost("fw_branch", cls=LinuxRouter, ip=None)

    net.addLink(
        switches["access_hq_a"],
        switches["core_hq"],
        intfName1="hqa-eth99",
        intfName2="core-eth01",
        cls=TCLink,
        bw=1000,
        delay="1ms",
    )
    net.addLink(
        switches["access_hq_b"],
        switches["core_hq"],
        intfName1="hqb-eth99",
        intfName2="core-eth02",
        cls=TCLink,
        bw=1000,
        delay="1ms",
    )
    net.addLink(
        switches["access_hq_c"],
        switches["core_hq"],
        intfName1="hqc-eth99",
        intfName2="core-eth03",
        cls=TCLink,
        bw=1000,
        delay="1ms",
    )
    net.addLink(
        switches["access_hq_it"],
        switches["core_hq"],
        intfName1="hqi-eth99",
        intfName2="core-eth07",
        cls=TCLink,
        bw=1000,
        delay="1ms",
    )
    net.addLink(
        switches["voice_access"],
        switches["core_hq"],
        intfName1="voice-eth99",
        intfName2="core-eth04",
        cls=TCLink,
        bw=500,
        delay="1ms",
    )
    net.addLink(
        switches["access_branch"],
        switches["dist_branch"],
        intfName1="br-eth99",
        intfName2="dist-eth01",
        cls=TCLink,
        bw=1000,
        delay="1ms",
    )

    net.addLink(
        switches["core_hq"], ce_hq,
        intfName1="core-eth05", intfName2="ce_hq-eth0",
        cls=TCLink, bw=200, delay="2ms",
    )
    net.addLink(
        ce_hq, mpls_cloud,
        intfName1="ce_hq-eth1", intfName2="mpls-eth01",
        cls=TCLink, bw=100, delay="10ms",
    )
    net.addLink(
        ce_branch, mpls_cloud,
        intfName1="ce_branch-eth1", intfName2="mpls-eth02",
        cls=TCLink, bw=100, delay="10ms",
    )
    net.addLink(
        switches["dist_branch"], ce_branch,
        intfName1="dist-eth02", intfName2="ce_branch-eth0",
        cls=TCLink, bw=200, delay="2ms",
    )

    net.addLink(
        switches["core_hq"], fw_hq,
        intfName1="core-eth06", intfName2="fw_hq-eth0",
        cls=TCLink, bw=200, delay="2ms",
    )
    net.addLink(
        fw_hq, internet,
        intfName1="fw_hq-eth1", intfName2="inet-eth01",
        cls=TCLink, bw=100, delay="5ms",
    )
    net.addLink(
        switches["dist_branch"], fw_branch,
        intfName1="dist-eth03", intfName2="fw_branch-eth0",
        cls=TCLink, bw=200, delay="2ms",
    )
    net.addLink(
        fw_branch, internet,
        intfName1="fw_branch-eth1", intfName2="inet-eth02",
        cls=TCLink, bw=100, delay="5ms",
    )

    info("*** Khá»Ÿi Ä‘á»™ng topology Hybrid MPLS L3VPN + SDN Edge Policy\n")
    net.build()
    controller.start()
    for switch in switches.values():
        switch.start([controller])
    mpls_cloud.start([])
    internet.start([])

    configure_routing(net, policy)
    start_service_simulators(net)

    emit()
    emit("=" * 88)
    emit(f"Topology da tao: {len(user_hosts)} user + 5 service")
    emit("Controller quan ly 8 OVS; CE, Firewall va MPLS Cloud khong dung OpenFlow.")
    emit("Lenh nhanh trong mininet:")
    emit("  testpolicy      # chay bang ping policy chi tiet")
    emit("  isolationflows  # xem DROP flow priority 400")
    emit("  h20_01 ping -c 2 h90")
    emit("=" * 88)
    if os.environ.get("CCH_AUTO_TEST_POLICY", "1") != "0":
        run_policy_tests(net, policy, title="Kiá»ƒm tra tá»± Ä‘á»™ng sau khi khá»Ÿi Ä‘á»™ng topology")
    else:
        emit("Bo qua auto-test vi CCH_AUTO_TEST_POLICY=0. Co the chay tay: testpolicy")
    CallCenterCLI(net, policy)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
