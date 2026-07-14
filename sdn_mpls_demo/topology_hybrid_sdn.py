#!/usr/bin/env python3
"""Topology 110 user cho Hybrid MPLS L3VPN + SDN Edge Policy."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import threading
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
CONTROL_SOCKET = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
CONTROL_TOKEN = os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
ALLOWED_CONTROL_COMMANDS = {
    "GET_TOPOLOGY",
    "GET_LINK_STATUS",
    "LINK_DOWN",
    "LINK_UP",
    "GET_HOST_STATUS",
    "GET_INTERFACE_MAP",
}

DPIDS = dpid_map(load_network_model())


LOGICAL_LINK_SEGMENTS = {
    "core_hq-ce_hq": [("hq_l3_gateway", "ce_hq")],
    "ce_hq-core_hq": [("hq_l3_gateway", "ce_hq")],
    "ce_branch-dist_branch": [("ce_branch", "branch_l3_gateway")],
    "dist_branch-ce_branch": [("ce_branch", "branch_l3_gateway")],
    "core_hq-fw_hq": [("hq_l3_gateway", "fw_hq")],
    "fw_hq-core_hq": [("hq_l3_gateway", "fw_hq")],
    "dist_branch-fw_branch": [("branch_l3_gateway", "fw_branch")],
    "fw_branch-dist_branch": [("branch_l3_gateway", "fw_branch")],
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


class MininetControlAgent:
    """Small allowlisted control plane for the dashboard.

    The FastAPI backend talks to this agent over a Unix socket. The agent runs
    inside the topology process, so LINK_DOWN/LINK_UP can call Mininet APIs
    against real interfaces instead of storing simulated state in the backend.
    """

    def __init__(self, net: Mininet, policy: dict):
        self.net = net
        self.policy = policy
        self.running = False
        self.thread: threading.Thread | None = None
        self.link_state: dict[str, str] = {}

    def start(self) -> None:
        try:
            CONTROL_SOCKET.unlink()
        except FileNotFoundError:
            pass
        self.running = True
        self.thread = threading.Thread(target=self._serve, name="cch-mininet-control", daemon=True)
        self.thread.start()
        emit(f"Mininet control agent: {CONTROL_SOCKET}")

    def stop(self) -> None:
        self.running = False
        try:
            CONTROL_SOCKET.unlink()
        except FileNotFoundError:
            pass

    def _serve(self) -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(CONTROL_SOCKET))
            CONTROL_SOCKET.chmod(0o660)
            server.listen(8)
            server.settimeout(1)
            while self.running:
                try:
                    conn, _addr = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.running:
                        raise
                    return
                with conn:
                    response = self._handle_connection(conn)
                    conn.sendall(json.dumps(response).encode("utf-8"))

    def _handle_connection(self, conn) -> dict:
        try:
            raw = conn.recv(65536).decode("utf-8").strip()
            request = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {"ok": False, "message": f"Invalid JSON: {exc}"}
        if request.get("token") != CONTROL_TOKEN:
            return {"ok": False, "message": "Unauthorized Mininet control request."}
        command = request.get("command")
        if command not in ALLOWED_CONTROL_COMMANDS:
            return {"ok": False, "message": f"Command not allowed: {command}"}
        if command == "GET_TOPOLOGY":
            return self._topology()
        if command == "GET_LINK_STATUS":
            return self._link_status()
        if command == "GET_HOST_STATUS":
            return self._host_status()
        if command == "GET_INTERFACE_MAP":
            return self._interface_map(request.get("link_id"))
        link_id = str(request.get("link_id", ""))
        if command == "LINK_DOWN":
            return self._set_link(link_id, "down")
        if command == "LINK_UP":
            return self._set_link(link_id, "up")
        return {"ok": False, "message": f"Unhandled command: {command}"}

    def _logical_links(self) -> list[str]:
        return [f"{source}-{target}" for source, target, _kind in self.policy.get("links", [])]

    def _segments_for_link(self, link_id: str) -> list[tuple[str, str]]:
        if link_id in LOGICAL_LINK_SEGMENTS:
            return LOGICAL_LINK_SEGMENTS[link_id]
        if "-" not in link_id:
            return []
        left, right = link_id.split("-", 1)
        groups = self.policy.get("host_groups", {})
        if left in groups and groups[left]["switch"] == right:
            group = groups[left]
            return [
                (f"{group['prefix']}_{index:02d}", right)
                for index in range(1, int(group["count"]) + 1)
            ]
        if right in groups and groups[right]["switch"] == left:
            group = groups[right]
            return [
                (left, f"{group['prefix']}_{index:02d}")
                for index in range(1, int(group["count"]) + 1)
            ]
        return [(left, right)]

    def _segment_interface_map(self, left: str, right: str) -> dict:
        try:
            left_node = self.net.get(left)
            right_node = self.net.get(right)
        except KeyError:
            return {"left": left, "right": right, "status": "missing", "interfaces": []}
        connections = left_node.connectionsTo(right_node)
        interfaces = [
            {
                "left": str(left_intf),
                "right": str(right_intf),
                "left_up": bool(left_intf.isUp()),
                "right_up": bool(right_intf.isUp()),
            }
            for left_intf, right_intf in connections
        ]
        if not interfaces:
            status = "missing"
        elif all(item["left_up"] and item["right_up"] for item in interfaces):
            status = "up"
        else:
            status = "down"
        return {"left": left, "right": right, "status": status, "interfaces": interfaces}

    def _link_runtime_status(self, link_id: str) -> str:
        if link_id in self.link_state:
            return self.link_state[link_id]
        segments = [self._segment_interface_map(left, right) for left, right in self._segments_for_link(link_id)]
        if not segments or any(item["status"] == "missing" for item in segments):
            return "unknown"
        return "up" if all(item["status"] == "up" for item in segments) else "down"

    def _set_link(self, link_id: str, state: str) -> dict:
        segments = self._segments_for_link(link_id)
        if not segments:
            return {"ok": False, "message": f"Khong tim thay mapping link {link_id}.", "link_id": link_id}
        changed = []
        for left, right in segments:
            try:
                self.net.configLinkStatus(left, right, state)
                changed.append({"left": left, "right": right, "state": state})
            except Exception as exc:  # Mininet raises generic Exception for missing links.
                return {
                    "ok": False,
                    "message": f"Khong doi duoc trang thai {left}-{right}: {exc}",
                    "link_id": link_id,
                    "changed": changed,
                }
        self.link_state[link_id] = state
        return {
            "ok": True,
            "available": True,
            "message": f"Da chuyen link {link_id} sang {state} tren Mininet.",
            "link_id": link_id,
            "status": state,
            "changed": changed,
            "links": self._link_status()["links"],
            "interfaces": self._interface_map(link_id).get("interfaces", []),
        }

    def _link_status(self) -> dict:
        return {
            "ok": True,
            "available": True,
            "links": {link_id: self._link_runtime_status(link_id) for link_id in self._logical_links()},
        }

    def _interface_map(self, link_id: str | None = None) -> dict:
        link_ids = [link_id] if link_id else self._logical_links()
        mapping = {
            item: [
                self._segment_interface_map(left, right)
                for left, right in self._segments_for_link(item)
            ]
            for item in link_ids
            if item
        }
        return {"ok": True, "available": True, "interfaces": mapping.get(link_id, mapping)}

    def _host_status(self) -> dict:
        nodes = getattr(self.net, "nameToNode", {})
        return {
            "ok": True,
            "available": True,
            "hosts": {name: name in nodes for name in self.policy.get("hosts", {})},
        }

    def _topology(self) -> dict:
        return {"ok": True, "available": True, **self._link_status()}


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
    ("IT support", "h70_01", "hcall", True, "IT Support can test declared Call App service"),
    ("IT least privilege", "h20_01", "h70_01", False, "Project users cannot initiate ping to IT"),
    ("IT least privilege", "h70_01", "hsocial", False, "IT Support is not full-access to Social Media"),
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
    engine = PolicyEngine(POLICY_FILE)
    data = dict(engine.data)
    data["links"] = NETWORK_MODEL["links"]
    data["hosts"] = engine.hosts
    return data


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
    hq_l3 = net.get("hq_l3_gateway")
    branch_l3 = net.get("branch_l3_gateway")
    ce_hq = net.get("ce_hq")
    ce_branch = net.get("ce_branch")
    fw_hq = net.get("fw_hq")
    fw_branch = net.get("fw_branch")

    configure_router_interface(
        hq_l3,
        "hq_l3-eth0",
        [
            "172.16.20.1/24",
            "172.16.30.1/24",
            "172.16.40.1/24",
            "172.16.70.1/24",
            "172.16.90.1/24",
        ],
    )
    configure_router_interface(hq_l3, "hq_l3-eth1", ["10.255.20.1/30"])
    configure_router_interface(hq_l3, "hq_l3-eth2", ["10.255.22.1/30"])
    configure_router_interface(ce_hq, "ce_hq-eth0", ["10.255.20.2/30"])
    configure_router_interface(ce_hq, "ce_hq-eth1", ["10.255.10.1/29"])

    configure_router_interface(
        branch_l3,
        "branch_l3-eth0",
        ["172.16.50.1/24", "172.16.60.1/24"],
    )
    configure_router_interface(branch_l3, "branch_l3-eth1", ["10.255.21.1/30"])
    configure_router_interface(branch_l3, "branch_l3-eth2", ["10.255.23.1/30"])
    configure_router_interface(ce_branch, "ce_branch-eth0", ["10.255.21.2/30"])
    configure_router_interface(ce_branch, "ce_branch-eth1", ["10.255.10.2/29"])

    configure_router_interface(fw_hq, "fw_hq-eth0", ["10.255.22.2/30"])
    configure_router_interface(fw_hq, "fw_hq-eth1", ["10.255.30.1/24"])
    configure_router_interface(fw_branch, "fw_branch-eth0", ["10.255.23.2/30"])
    configure_router_interface(fw_branch, "fw_branch-eth1", ["10.255.30.2/24"])

    for prefix in ("172.16.50.0/24", "172.16.60.0/24"):
        add_route(hq_l3, prefix, "10.255.20.2")
        add_route(ce_hq, prefix, "10.255.10.2")
    for prefix in ("172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.70.0/24", "172.16.90.0/24"):
        add_route(branch_l3, prefix, "10.255.21.2")
        add_route(ce_branch, prefix, "10.255.10.1")
        add_route(ce_hq, prefix, "10.255.20.1")
    for prefix in ("172.16.50.0/24", "172.16.60.0/24"):
        add_route(ce_branch, prefix, "10.255.21.1")
    add_route(hq_l3, "0.0.0.0/0", "10.255.22.2")
    add_route(branch_l3, "0.0.0.0/0", "10.255.23.2")

    for prefix in ("172.16.20.0/24", "172.16.30.0/24", "172.16.40.0/24", "172.16.70.0/24", "172.16.90.0/24"):
        add_route(fw_hq, prefix, "10.255.22.1")
    for prefix in ("172.16.50.0/24", "172.16.60.0/24"):
        add_route(fw_branch, prefix, "10.255.23.1")

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

    hq_l3 = net.addHost("hq_l3_gateway", cls=LinuxRouter, ip=None)
    branch_l3 = net.addHost("branch_l3_gateway", cls=LinuxRouter, ip=None)
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
        switches["core_hq"], hq_l3,
        intfName1="core-eth05", intfName2="hq_l3-eth0",
        cls=TCLink, bw=1000, delay="1ms",
    )
    net.addLink(
        hq_l3, ce_hq,
        intfName1="hq_l3-eth1", intfName2="ce_hq-eth0",
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
        switches["dist_branch"], branch_l3,
        intfName1="dist-eth02", intfName2="branch_l3-eth0",
        cls=TCLink, bw=1000, delay="1ms",
    )
    net.addLink(
        branch_l3, ce_branch,
        intfName1="branch_l3-eth1", intfName2="ce_branch-eth0",
        cls=TCLink, bw=200, delay="2ms",
    )

    net.addLink(
        hq_l3, fw_hq,
        intfName1="hq_l3-eth2", intfName2="fw_hq-eth0",
        cls=TCLink, bw=200, delay="2ms",
    )
    net.addLink(
        fw_hq, internet,
        intfName1="fw_hq-eth1", intfName2="inet-eth01",
        cls=TCLink, bw=100, delay="5ms",
    )
    net.addLink(
        branch_l3, fw_branch,
        intfName1="branch_l3-eth2", intfName2="fw_branch-eth0",
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
    control_agent = MininetControlAgent(net, policy)
    control_agent.start()

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
    try:
        CallCenterCLI(net, policy)
    finally:
        control_agent.stop()
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
