#!/usr/bin/env python3
"""Ubuntu live acceptance for the Phase 44 two-site nftables firewall."""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.network_model import build_host_inventory, load_network_model
from sdn_mpls_demo.firewall_nftables import (
    FIREWALL_NAMES,
    NFT_FAMILY,
    NFT_TABLE,
    apply_named_namespaces,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT_DIR / "runtime_reports"
INVENTORY_FILE = ROOT_DIR / "sdn_mpls_demo" / "runtime" / "phase42_topology_runtime.json"
CONTROLLER_LOG = ROOT_DIR / "sdn_mpls_demo" / "runtime" / "controller.log"
CONTROL_SOCKET = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
CONTROL_TOKEN = os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
ERROR_PATTERNS = (
    "Traceback",
    "BrokenPipeError",
    "Connection refused",
    "nft syntax error",
    "rule apply failure",
    "namespace missing",
    "route missing",
    "duplicate rule",
    "FAILED",
    "CRITICAL",
)


class RuntimeCheckError(RuntimeError):
    pass


class Reporter:
    def __init__(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = REPORT_DIR / f"phase44_firewall_{timestamp}.log"
        self.json_path = REPORT_DIR / f"phase44_firewall_{timestamp}.json"
        self.results: list[dict[str, Any]] = []
        self.lines: list[str] = []

    def log(self, value: Any = "") -> None:
        line = str(value)
        print(line, flush=True)
        self.lines.append(line)

    def record(self, name: str, passed: bool, **details: Any) -> None:
        status = "PASS" if passed else "FAIL"
        item = {"name": name, "status": status, **details}
        self.results.append(item)
        self.log(f"{status:<4} {name}: {json.dumps(details, ensure_ascii=False, default=str)}")

    def save(self, nat_conclusion: str) -> None:
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "passed": all(item["status"] == "PASS" for item in self.results),
            "nat_conclusion": nat_conclusion,
            "results": self.results,
        }
        self.log_path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        self.json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.log(f"LOG={self.log_path}")
        self.log(f"JSON={self.json_path}")


def run(command: list[str], reporter: Reporter, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    reporter.log(f"$ {' '.join(command)}")
    if result.stdout:
        reporter.log(result.stdout.rstrip())
    if result.stderr:
        reporter.log(result.stderr.rstrip())
    reporter.log(f"EXIT_CODE={result.returncode} DURATION={time.monotonic() - started:.3f}s")
    if check and result.returncode != 0:
        raise RuntimeCheckError(f"Command failed: {' '.join(command)}")
    return result


def agent_request(command: str, **payload: Any) -> dict[str, Any]:
    request = {"token": CONTROL_TOKEN, "command": command, **payload}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(20)
        client.connect(str(CONTROL_SOCKET))
        client.sendall((json.dumps(request) + "\n").encode("utf-8"))
        chunks = bytearray()
        while b"\n" not in chunks:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.extend(chunk)
    if not chunks:
        raise RuntimeCheckError(f"Agent did not answer {command}")
    response = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
    if not isinstance(response, dict):
        raise RuntimeCheckError(f"Agent response for {command} is not an object")
    return response


def nft_table(namespace: str, reporter: Reporter, *, json_output: bool = False) -> subprocess.CompletedProcess[str]:
    command = ["ip", "netns", "exec", namespace, "nft"]
    if json_output:
        command.append("--json")
    command.extend(["list", "table", NFT_FAMILY, NFT_TABLE])
    return run(command, reporter, check=True)


def nft_counters(namespace: str, reporter: Reporter) -> tuple[int, dict[str, int], str]:
    result = nft_table(namespace, reporter, json_output=True)
    payload = json.loads(result.stdout)
    counters: dict[str, int] = {}
    rule_count = 0
    for item in payload.get("nftables", []):
        rule = item.get("rule") if isinstance(item, dict) else None
        if not isinstance(rule, dict):
            continue
        rule_count += 1
        comment = str(rule.get("comment") or "")
        packets = 0
        for expression in rule.get("expr", []):
            counter = expression.get("counter") if isinstance(expression, dict) else None
            if isinstance(counter, dict):
                packets = int(counter.get("packets", 0))
        if comment:
            counters[comment] = packets
    return rule_count, counters, result.stdout


def ping(source: str, destination: str, hosts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return agent_request(
        "PING",
        source=source,
        destination_ip=hosts[destination]["ip"],
        count=3,
    )


def check_ping_counter(
    reporter: Reporter,
    hosts: dict[str, dict[str, Any]],
    name: str,
    source: str,
    destination: str,
    expected: bool,
    namespace: str | None = None,
    comment: str | None = None,
) -> None:
    before = None
    if namespace and comment:
        _count, counters, _raw = nft_counters(namespace, reporter)
        before = counters.get(comment)
    started = time.monotonic()
    response = ping(source, destination, hosts)
    reachable = bool(response.get("ok"))
    after = None
    if namespace and comment:
        _count, counters, _raw = nft_counters(namespace, reporter)
        after = counters.get(comment)
    counter_ok = before is None or (after is not None and after > before)
    reporter.record(
        name,
        reachable is expected and counter_ok,
        source=source,
        destination=destination,
        expected="ALLOW" if expected else "DENY",
        reachable=reachable,
        counter_comment=comment,
        packets_before=before,
        packets_after=after,
        duration=round(time.monotonic() - started, 3),
        response_summary=str(response.get("raw") or response.get("message") or "")[-500:],
    )


def flow_packets(bridge: str, source: str, destination: str, reporter: Reporter) -> int | None:
    result = run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", bridge], reporter, check=True)
    for line in result.stdout.splitlines():
        if all(token in line for token in ("cookie=0x1002", f"nw_src={source}", f"nw_dst={destination}", "actions=drop")):
            match = re.search(r"n_packets=(\d+)", line)
            return int(match.group(1)) if match else None
    return None


def prove_no_nat_source_translation(
    reporter: Reporter,
    inventory: dict[str, Any],
    hosts: dict[str, dict[str, Any]],
) -> bool:
    pid = str(inventory.get("namespace_pids", {}).get("hcall", ""))
    source_ip = str(hosts["h20_01"]["ip"])
    if not pid.isdigit():
        reporter.record("NAT source capture", False, reason="Missing hcall namespace PID")
        return False
    command = [
        "mnexec", "-a", pid, "timeout", "8", "tcpdump", "-n", "-l", "-i", "any", "-c", "1",
        "icmp", "and", "src", "host", source_ip,
    ]
    capture = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.4)
    response = ping("h20_01", "hcall", hosts)
    stdout, stderr = capture.communicate(timeout=10)
    reporter.log(f"$ {' '.join(command)}")
    reporter.log(stdout.rstrip())
    reporter.log(stderr.rstrip())
    observed = source_ip in stdout and bool(response.get("ok"))
    reporter.record(
        "NAT source capture",
        observed,
        expected_source=source_ip,
        source_observed=source_ip if source_ip in stdout else None,
        ping_ok=bool(response.get("ok")),
    )
    return observed


def main() -> int:
    reporter = Reporter()
    nat_conclusion = "NAT REQUIREMENT NOT YET CONCLUDED"
    try:
        if sys.platform != "linux":
            raise RuntimeCheckError("Phase 44 runtime check only runs on Linux")
        if os.geteuid() != 0:
            raise RuntimeCheckError("Run with sudo so nftables/netns/OVS counters are readable")

        branch = run(["git", "branch", "--show-current"], reporter, check=True)
        head = run(["git", "rev-parse", "--short", "HEAD"], reporter, check=True)
        status = run(["git", "status", "--short"], reporter, check=True)
        reporter.record(
            "Git checkpoint",
            branch.stdout.strip() == "feature/dual-branch-topology" and not status.stdout.strip(),
            branch=branch.stdout.strip(),
            head=head.stdout.strip(),
            clean=not status.stdout.strip(),
        )

        health = agent_request("HEALTH")
        reporter.record("Mininet Control Agent HEALTH", bool(health.get("ok") and health.get("agent_alive")), response=health)
        netns = run(["ip", "netns", "list"], reporter, check=True)
        names = {line.split()[0] for line in netns.stdout.splitlines() if line.strip()}
        reporter.record("Named firewall namespaces", set(FIREWALL_NAMES).issubset(names), namespaces=sorted(names))

        ovs = run(["ovs-vsctl", "show"], reporter, check=True)
        reporter.record("Nine OVS connected", ovs.stdout.count("is_connected: true") == 9, connected=ovs.stdout.count("is_connected: true"))

        inventory = json.loads(INVENTORY_FILE.read_text(encoding="utf-8"))
        hosts = build_host_inventory(load_network_model())
        initial_counts: dict[str, int] = {}
        initial_rulesets: dict[str, str] = {}
        initial_established: dict[str, int] = {}
        for firewall in FIREWALL_NAMES:
            count, counters, raw = nft_counters(firewall, reporter)
            initial_counts[firewall] = count
            initial_rulesets[firewall] = raw
            initial_established[firewall] = counters.get(f"cch:{firewall}:forward-established", 0)
            forward = run(["ip", "netns", "exec", firewall, "sysctl", "net.ipv4.ip_forward"], reporter, check=True)
            reporter.record(f"{firewall} forwarding", forward.stdout.strip().endswith("= 1"), output=forward.stdout.strip())

        cases = (
            ("HQ Project A -> Call", "h20_01", "hcall", True, "fw_hq", "cch:fw_hq:allow-call-app:hcall"),
            ("HQ Project A -> Zalo", "h20_01", "hzalo", True, "fw_hq", "cch:fw_hq:allow-zalo:hzalo"),
            ("HQ Project A -> Social", "h20_01", "hsocial", False, "fw_hq", "cch:fw_hq:deny-social-media:hsocial"),
            ("BackOffice -> Call", "h60_01", "hcall", True, "fw_hq", "cch:fw_hq:allow-call-app:hcall"),
            ("BackOffice -> Zalo", "h60_01", "hzalo", True, "fw_hq", "cch:fw_hq:allow-zalo:hzalo"),
            ("BackOffice -> Social", "h60_01", "hsocial", False, "fw_hq", "cch:fw_hq:deny-social-media:hsocial"),
            ("Telesale -> Call", "h50_01", "hcall", True, "fw_telesale", "cch:fw_telesale:allow-call-app:hcall"),
            ("Telesale -> Zalo", "h50_01", "hzalo", True, "fw_telesale", "cch:fw_telesale:allow-zalo:hzalo"),
            ("Telesale -> Social", "h50_01", "hsocial", False, "fw_telesale", "cch:fw_telesale:deny-social-media:hsocial"),
            ("Internet -> Project A", "hinternet", "h20_01", False, "fw_hq", "cch:fw_hq:deny-inbound-new"),
            ("Internet -> BackOffice", "hinternet", "h60_01", False, "fw_hq", "cch:fw_hq:deny-inbound-new"),
            ("Internet -> Telesale", "hinternet", "h50_01", False, "fw_telesale", "cch:fw_telesale:deny-inbound-new"),
            ("BackOffice -> Voice", "h60_01", "h90", True, None, None),
            ("Telesale -> Voice", "h50_01", "h90", True, None, None),
        )
        for case in cases:
            check_ping_counter(reporter, hosts, *case)

        for firewall in FIREWALL_NAMES:
            _count, counters, _raw = nft_counters(firewall, reporter)
            after = counters.get(f"cch:{firewall}:forward-established", 0)
            reporter.record(
                f"{firewall} established return counter",
                after > initial_established[firewall],
                packets_before=initial_established[firewall],
                packets_after=after,
            )

        isolation = (
            ("Telesale -> BackOffice OpenFlow", "dist_telesale", "172.16.50.0/24", "172.16.60.0/24", "h50_01", "h60_01"),
            ("BackOffice -> Telesale OpenFlow", "core_hq", "172.16.60.0/24", "172.16.50.0/24", "h60_01", "h50_01"),
        )
        for name, bridge, src_net, dst_net, source, destination in isolation:
            before = flow_packets(bridge, src_net, dst_net, reporter)
            response = ping(source, destination, hosts)
            after = flow_packets(bridge, src_net, dst_net, reporter)
            reporter.record(name, response.get("ok") is False and before is not None and after is not None and after > before, packets_before=before, packets_after=after)

        counts_before_reload = dict(initial_counts)
        reload_result = apply_named_namespaces()
        for firewall in FIREWALL_NAMES:
            count, _counters, _raw = nft_counters(firewall, reporter)
            reporter.record(
                f"{firewall} idempotent reload",
                count == counts_before_reload[firewall] == int(reload_result[firewall]["rule_count"]),
                before=counts_before_reload[firewall],
                after=count,
            )

        check_ping_counter(
            reporter, hosts, "Post-reload HQ -> Call", "h20_01", "hcall", True,
            "fw_hq", "cch:fw_hq:allow-call-app:hcall",
        )

        no_nat = all(
            not re.search(r"\b(masquerade|snat)\b", ruleset, flags=re.IGNORECASE)
            for ruleset in initial_rulesets.values()
        )
        route_ok = True
        for node_name in ("fw_hq", "fw_telesale", "hcall", "hzalo", "hsocial", "hinternet"):
            pid = str(inventory.get("namespace_pids", {}).get(node_name, ""))
            if not pid.isdigit():
                route_ok = False
                reporter.record(f"Route {node_name}", False, reason="Missing namespace PID")
                continue
            route = run(["mnexec", "-a", pid, "ip", "-4", "route", "show"], reporter, check=True)
            has_route = bool(route.stdout.strip()) and "default via" in route.stdout
            route_ok = route_ok and has_route
            reporter.record(f"Route {node_name}", has_route, routes=route.stdout.strip())
        source_preserved = prove_no_nat_source_translation(reporter, inventory, hosts)
        if no_nat and route_ok and source_preserved:
            nat_conclusion = "NAT NOT REQUIRED AND RUNTIME PROVEN"
        reporter.record("No NAT rules", no_nat, conclusion=nat_conclusion)

        log_text = CONTROLLER_LOG.read_text(encoding="utf-8", errors="replace") if CONTROLLER_LOG.exists() else ""
        found = [pattern for pattern in ERROR_PATTERNS if pattern.lower() in log_text.lower()]
        reporter.record("Runtime error scan", not found, patterns=found)
    except Exception as exc:  # noqa: BLE001 - acceptance runner must persist every failure.
        reporter.record("Runtime checker", False, error_type=type(exc).__name__, message=str(exc))

    reporter.save(nat_conclusion)
    return 0 if all(item["status"] == "PASS" for item in reporter.results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
