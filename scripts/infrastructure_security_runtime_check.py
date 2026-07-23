#!/usr/bin/env python3
"""Ubuntu live validation for infrastructure security controls.

The script uses real Mininet Control Agent PING responses, live OVS flow
queries and live nftables counters. A static policy decision alone is never
counted as runtime evidence.
"""

from __future__ import annotations

import json
import os
import platform
import re
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.infrastructure_security_check import SECURITY_CASES, audit
from scripts.network_model import build_host_inventory, load_network_model, runtime_switch_name
from sdn_mpls_demo.policy_engine import PolicyEngine


CONTROL_SOCKET = Path(os.environ.get("CCH_MININET_CONTROL_SOCKET", "/tmp/cch_mininet_control.sock"))
CONTROL_TOKEN = os.environ.get("CCH_MININET_CONTROL_TOKEN", "cch-local-mininet-token")
REPORT_DIR = ROOT_DIR / "runtime_reports"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG_FILE = REPORT_DIR / f"infrastructure_security_{STAMP}.log"
JSON_FILE = REPORT_DIR / f"infrastructure_security_{STAMP}.json"
RESULTS: list[dict[str, Any]] = []


def log(message: str) -> None:
    print(message, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def record(name: str, passed: bool, started: float, *, error_code: str | None = None, summary: Any = None) -> bool:
    item = {
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "duration_seconds": round(time.monotonic() - started, 3),
        "error_code": error_code,
        "response_summary": summary,
    }
    RESULTS.append(item)
    log(
        f"{item['status']:<4} {name} duration={item['duration_seconds']:.3f}s "
        f"error_code={error_code or '-'} summary={json.dumps(summary, ensure_ascii=False, default=str)}"
    )
    return passed


def run_case(name: str, function) -> bool:
    started = time.monotonic()
    try:
        passed, error_code, summary = function()
    except Exception as exc:
        passed, error_code, summary = False, type(exc).__name__, str(exc)[:500]
    return record(name, passed, started, error_code=error_code, summary=summary)


def agent_request(command: str, **payload: Any) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    request = {"token": CONTROL_TOKEN, "command": command, "request_id": request_id, **payload}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(15)
        client.connect(str(CONTROL_SOCKET))
        client.sendall((json.dumps(request) + "\n").encode("utf-8"))
        chunks = bytearray()
        while b"\n" not in chunks:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.extend(chunk)
    if not chunks:
        raise RuntimeError(f"Agent khong tra loi lenh {command}")
    response = json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))
    if response.get("request_id") != request_id:
        raise RuntimeError(f"Agent request_id khong khop cho {command}")
    return response


def command(args: list[str], timeout: float = 15) -> tuple[int, str]:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    return result.returncode, (result.stdout + result.stderr).strip()


def flow_dump(switch: str) -> tuple[bool, str]:
    code, output = command(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", switch])
    return code == 0 and "actions=" in output, output


def isolation_flow_case(switch: str) -> tuple[bool, str | None, Any]:
    available, output = flow_dump(switch)
    has_drop = "priority=400" in output and "actions=drop" in output
    passed = available and has_drop
    return passed, None if passed else "ISOLATION_FLOW_NOT_FOUND", {
        "switch": switch,
        "openflow13_dump_available": available,
        "priority_400_drop_present": has_drop,
    }


def openflow_dump_case(switch: str) -> tuple[bool, str | None, Any]:
    available, _output = flow_dump(switch)
    return available, None if available else "FLOW_INVENTORY_UNAVAILABLE", {
        "runtime_bridge": switch,
        "openflow13_dump_available": available,
    }


def firewall_counter(response: dict[str, Any], firewall: str, counter_name: str) -> int | None:
    item = response.get("firewalls", {}).get(firewall, {})
    counter = item.get("counters", {}).get(counter_name)
    return int(counter["packets"]) if isinstance(counter, dict) and counter.get("packets") is not None else None


def ping_case(case, hosts: dict[str, dict[str, Any]]) -> tuple[bool, str | None, Any]:
    destination_ip = hosts[case.destination]["ip"]
    response = agent_request("PING", source=case.source, destination_ip=destination_ip, count=2)
    raw = str(response.get("raw") or "")
    match = re.search(r"([0-9.]+)% packet loss", raw)
    reachable = bool(response.get("ok") and match and float(match.group(1)) < 100)
    expected = case.expected_action == "allow"
    passed = reachable == expected
    return passed, None if passed else "RUNTIME_POLICY_MISMATCH", {
        "source": case.source,
        "destination": case.destination,
        "expected": "ALLOW" if expected else "DENY",
        "actual": "ALLOW" if reachable else "DENY",
        "blocked_at_from_policy": case.expected_blocked_at,
        "packet_loss_percent": float(match.group(1)) if match else None,
        "raw_tail": raw[-240:],
    }


def write_report() -> None:
    passed = sum(item["status"] == "PASS" for item in RESULTS)
    report = {
        "suite": "Infrastructure security Ubuntu live runtime",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "failed": len(RESULTS) - passed,
        "total": len(RESULTS),
        "results": RESULTS,
        "runtime_evidence": "Mininet Control Agent PING, OVS OpenFlow dump, nftables FIREWALL_STATUS",
        "log_file": str(LOG_FILE.relative_to(ROOT_DIR)),
    }
    JSON_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"ARTIFACT log={LOG_FILE.relative_to(ROOT_DIR)}")
    log(f"ARTIFACT json={JSON_FILE.relative_to(ROOT_DIR)}")
    log(f"RESULT {passed}/{len(RESULTS)} LIVE CHECKS PASS")


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("", encoding="utf-8")
    if platform.system() != "Linux":
        log("PENDING Ubuntu runtime: script chi chay tren Linux.")
        return 2
    if os.geteuid() != 0:
        log("FAIL Can chay bang sudo de doc OVS, namespace va nftables.")
        return 2

    static_results = audit()
    run_case(
        "static_policy_audit",
        lambda: (
            all(passed for _name, passed, _detail in static_results),
            "STATIC_POLICY_FAILED" if not all(passed for _name, passed, _detail in static_results) else None,
            {"checks": len(static_results), "passed": sum(passed for _name, passed, _detail in static_results)},
        ),
    )
    run_case("control_agent_socket", lambda: (CONTROL_SOCKET.is_socket(), "AGENT_NOT_READY", str(CONTROL_SOCKET)))
    run_case(
        "control_agent_health",
        lambda: (
            bool((response := agent_request("HEALTH")).get("ok") and response.get("agent_alive")),
            None,
            {"ok": response.get("ok"), "agent_alive": response.get("agent_alive")},
        ),
    )

    model = load_network_model()
    hosts = build_host_inventory(model)
    live_status: dict[str, Any] = {}

    def live_inventory_case() -> tuple[bool, str | None, Any]:
        live_status.update(agent_request("LIVE_STATUS"))
        expected_names = set(hosts)
        actual_names = {name for name, online in live_status.get("hosts", {}).items() if online}
        passed = live_status.get("ok") is True and live_status.get("user_hosts_online") == 110 and expected_names.issubset(actual_names)
        return passed, None if passed else "TOPOLOGY_INCOMPLETE", {
            "user_hosts_online": live_status.get("user_hosts_online"),
            "expected_endpoints": len(expected_names),
            "online_endpoints": len(actual_names),
        }

    run_case("live_inventory_110_users_115_endpoints", live_inventory_case)

    for logical, data in model["switches"].items():
        if not data.get("controlled"):
            continue
        runtime = runtime_switch_name(model, logical)
        run_case(
            f"ovs_bridge_{logical}",
            lambda runtime=runtime: (
                command(["ovs-vsctl", "br-exists", runtime])[0] == 0,
                "OVS_UNAVAILABLE",
                {"runtime_bridge": runtime},
            ),
        )
    for logical in ("core_hq", "dist_telesale"):
        runtime = runtime_switch_name(model, logical)
        run_case(
            f"openflow_dump_{logical}",
            lambda runtime=runtime: openflow_dump_case(runtime),
        )
        run_case(f"isolation_drop_{logical}", lambda runtime=runtime: isolation_flow_case(runtime))

    firewall_before: dict[str, Any] = {}

    def firewall_status_case() -> tuple[bool, str | None, Any]:
        firewall_before.update(agent_request("FIREWALL_STATUS"))
        firewalls = firewall_before.get("firewalls", {})
        passed = firewall_before.get("ok") is True and set(firewalls) == {"fw_hq", "fw_telesale"} and all(
            item.get("ok") and item.get("ipv4_forwarding") and int(item.get("rule_count", 0)) > 0
            for item in firewalls.values()
        )
        return passed, None if passed else "FIREWALL_UNAVAILABLE", {
            name: {"ok": item.get("ok"), "rule_count": item.get("rule_count"), "ipv4_forwarding": item.get("ipv4_forwarding")}
            for name, item in firewalls.items()
        }

    run_case("firewall_live_status", firewall_status_case)

    for case in SECURITY_CASES:
        run_case(f"ping_{case.source}_to_{case.destination}", lambda case=case: ping_case(case, hosts))

    def hq_social_counter_case() -> tuple[bool, str | None, Any]:
        before = firewall_counter(firewall_before, "fw_hq", "social_deny")
        if before is None:
            return False, "FIREWALL_COUNTER_UNAVAILABLE", {"firewall": "fw_hq", "counter": "social_deny"}
        case = next(item for item in SECURITY_CASES if item.source == "h20_01" and item.destination == "hsocial")
        ping_case(case, hosts)
        after_response = agent_request("FIREWALL_STATUS")
        after = firewall_counter(after_response, "fw_hq", "social_deny")
        passed = after is not None and after > before
        return passed, None if passed else "FIREWALL_COUNTER_NOT_INCREASED", {"before": before, "after": after}

    def inbound_counter_case() -> tuple[bool, str | None, Any]:
        before = firewall_counter(firewall_before, "fw_hq", "inbound_deny")
        if before is None:
            return False, "FIREWALL_COUNTER_UNAVAILABLE", {"firewall": "fw_hq", "counter": "inbound_deny"}
        case = next(item for item in SECURITY_CASES if item.source == "hinternet" and item.destination == "h20_01")
        ping_case(case, hosts)
        after_response = agent_request("FIREWALL_STATUS")
        after = firewall_counter(after_response, "fw_hq", "inbound_deny")
        passed = after is not None and after > before
        return passed, None if passed else "FIREWALL_COUNTER_NOT_INCREASED", {"before": before, "after": after}

    run_case("hq_social_deny_counter_increases", hq_social_counter_case)
    run_case("hq_inbound_deny_counter_increases", inbound_counter_case)

    write_report()
    return 0 if RESULTS and all(item["status"] == "PASS" for item in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
