#!/usr/bin/env python3
"""Topology 104 user cho Hybrid MPLS L3VPN + SDN Edge Policy."""

from __future__ import annotations

import ipaddress
import os
import re
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
    "access_hq_it": "0000000000000008",
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


POLICY_TESTS = (
    ("Project isolation", "h20_01", "h30_01", False, "Project A không được ping Project B"),
    ("Project isolation", "h20_01", "h40_01", False, "Project A không được ping Project C"),
    ("Project isolation", "h30_01", "h20_01", False, "Project B không được ping Project A"),
    ("Project isolation", "h30_01", "h40_01", False, "Project B không được ping Project C"),
    ("Project isolation", "h40_01", "h20_01", False, "Project C không được ping Project A"),
    ("Project isolation", "h40_01", "h30_01", False, "Project C không được ping Project B"),
    ("Branch isolation", "h50_01", "h60_01", False, "Telesale không được ping BackOffice"),
    ("Branch isolation", "h60_01", "h50_01", False, "BackOffice không được ping Telesale"),
    ("Voice", "h20_01", "h90", True, "Project A được ping Voice"),
    ("Voice", "h30_01", "h90", True, "Project B được ping Voice"),
    ("Voice", "h40_01", "h90", True, "Project C được ping Voice"),
    ("Voice", "h50_01", "h90", True, "Telesale được ping Voice qua MPLS"),
    ("Voice", "h60_01", "h90", True, "BackOffice được ping Voice qua MPLS"),
    ("Voice", "h70_01", "h90", True, "IT Support được ping Voice"),
    ("Internet services", "h20_01", "hzalo", True, "Project A được dùng Zalo qua Firewall HQ"),
    ("Internet services", "h20_01", "hcall", True, "Project A được dùng Call App qua Firewall HQ"),
    ("Internet services", "h20_01", "hinternet", True, "Project A được dùng Internet test qua Firewall HQ"),
    ("Internet services", "h50_01", "hzalo", True, "Telesale được dùng Zalo qua Firewall Branch"),
    ("Internet services", "h50_01", "hcall", True, "Telesale được dùng Call App qua Firewall Branch"),
    ("Internet services", "h60_01", "hinternet", True, "BackOffice được dùng Internet test qua Firewall Branch"),
    ("Social block", "h20_01", "hsocial", False, "Project A bị chặn Social Media tại Firewall HQ"),
    ("Social block", "h30_01", "hsocial", False, "Project B bị chặn Social Media tại Firewall HQ"),
    ("Social block", "h40_01", "hsocial", False, "Project C bị chặn Social Media tại Firewall HQ"),
    ("Social block", "h50_01", "hsocial", False, "Telesale bị chặn Social Media tại Firewall Branch"),
    ("Social block", "h60_01", "hsocial", False, "BackOffice bị chặn Social Media tại Firewall Branch"),
    ("Controlled intersite", "h50_01", "h20_01", True, "Telesale được ping Project A theo rule liên site"),
    ("Controlled intersite", "h20_01", "h50_01", True, "Project A được ping Telesale theo rule liên site"),
    ("Controlled intersite", "h60_01", "h20_01", False, "BackOffice không có full access vào Project A"),
    ("Controlled intersite", "h20_01", "h60_01", False, "Project A không có full access vào BackOffice"),
    ("IT support", "h70_01", "h20_01", True, "IT Support được remote Project A"),
    ("IT support", "h70_01", "h30_01", True, "IT Support được remote Project B"),
    ("IT support", "h70_01", "h50_01", True, "IT Support được remote Telesale qua MPLS"),
    ("IT support", "h70_01", "hsocial", True, "IT Support được kiểm tra dịch vụ social"),
    ("Internet inbound", "hinternet", "h20_01", False, "Internet ngoài không được chủ động ping Project A"),
    ("Internet inbound", "hzalo", "h30_01", False, "Zalo simulator không được chủ động ping Project B"),
    ("Internet inbound", "hcall", "h50_01", False, "Call App simulator không được chủ động ping Telesale"),
    ("Internet inbound", "hsocial", "h60_01", False, "Social simulator không được chủ động ping BackOffice"),
    ("Internet inbound", "hinternet", "h70_01", False, "Internet ngoài không được chủ động ping IT"),
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


def short_text(value, width):
    value = str(value)
    return value if len(value) <= width else value[: width - 3] + "..."


def run_policy_tests(net, policy, title="Kiểm tra policy bằng ping thật"):
    width = 124
    emit()
    emit("=" * width)
    emit(f"{title}")
    emit("PASS = ping thật khớp policy. FAIL = cần xem controller.log / dump-flows.")
    emit("=" * width)
    emit(
        f"{'STT':<4} {'NHOM POLICY':<21} {'SOURCE':<10} {'DEST':<10} "
        f"{'POLICY':<7} {'PING':<7} {'KQ':<6} GHI CHU"
    )
    emit("-" * width)
    passed = 0
    for index, (category, source_name, destination_name, expected, reason) in enumerate(POLICY_TESTS, start=1):
        reachable, _output = ping_reachable(net, policy, source_name, destination_name)
        matched = reachable == expected
        passed += int(matched)
        emit(
            f"{index:<4} {short_text(category, 21):<21} {source_name:<10} {destination_name:<10} "
            f"{'ALLOW' if expected else 'DENY':<7} {'ALLOW' if reachable else 'DENY':<7} "
            f"{'PASS' if matched else 'FAIL':<6} {short_text(reason, 52)}"
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
        "Chạy ma trận ping chi tiết theo policy ALLOW/DENY."
        run_policy_tests(self.mn, self.policy, title="Kiểm tra policy thủ công bằng ping thật")

    def do_isolationflows(self, _line):
        "Hiển thị các flow DROP priority 400 trên OVS."
        info("\n*** Isolation flow priority 400\n")
        for switch_name in DPIDS:
            switch = self.mn.get(switch_name)
            info(f"\n--- {switch_name} ---\n")
            info(switch.cmd(
                f"ovs-ofctl -O OpenFlow13 dump-flows {switch_name} "
                f"| grep 'priority=400' || true"
            ))


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
    # Mininet chỉ tự sinh DPID cho tên canonical như s1/s23. Hai bridge
    # standalone vẫn cần DPID tường minh dù không kết nối SDN Controller.
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
    h90 = net.addHost("h90", ip="172.16.90.10/24", defaultRoute="via 172.16.90.1")
    net.addLink(
        h90,
        switches["voice_mgmt"],
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
        switches["voice_mgmt"],
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

    info("*** Khởi động topology Hybrid MPLS L3VPN + SDN Edge Policy\n")
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
        run_policy_tests(net, policy, title="Kiểm tra tự động sau khi khởi động topology")
    else:
        emit("Bo qua auto-test vi CCH_AUTO_TEST_POLICY=0. Co the chay tay: testpolicy")
    CallCenterCLI(net, policy)
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
