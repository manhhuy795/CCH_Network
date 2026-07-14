from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import repo  # Đảm bảo repository root có trong sys.path.
from scripts.network_model import architecture_links, controlled_switches, load_network_model
from sdn_mpls_demo.policy_engine import GROUP_PATHS, PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_FILE = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
RUNTIME_FLOWS_FILE = REPO_ROOT / "sdn_mpls_demo" / "runtime" / "installed_flows.json"
NETWORK_MODEL = load_network_model()
ENGINE = PolicyEngine(POLICY_FILE)
CONTROLLED_SWITCHES = controlled_switches(NETWORK_MODEL)

CLUSTER_SOURCES = {
    "project_a": ("h20_01", "Dự án A / VLAN 20"),
    "project_b": ("h30_01", "Dự án B / VLAN 30"),
    "project_c": ("h40_01", "Dự án C / VLAN 40"),
    "telesale": ("h50_01", "Telesale / VLAN 50"),
    "backoffice": ("h60_01", "BackOffice / VLAN 60"),
    "it_support": ("h70_01", "IT Support / VLAN 70"),
}

CLUSTER_ALLOW_TARGETS = {
    "project_a": ("h90", "hzalo", "hcall", "hinternet"),
    "project_b": ("h90", "hzalo", "hcall", "hinternet"),
    "project_c": ("h90", "hzalo", "hcall", "hinternet"),
    "telesale": ("h90", "hzalo", "hcall", "hinternet"),
    "backoffice": ("h90", "hzalo", "hcall", "hinternet"),
    "it_support": ("h20_01", "h30_01", "h40_01", "h50_01", "h60_01", "h90", "hcall", "hsocial"),
}

CLUSTER_DENY_TARGETS = {
    "project_a": ("h30_01", "h40_01", "h50_01", "h60_01", "hsocial"),
    "project_b": ("h20_01", "h40_01", "h50_01", "h60_01", "hsocial"),
    "project_c": ("h20_01", "h30_01", "h50_01", "h60_01", "hsocial"),
    "telesale": ("h20_01", "h30_01", "h40_01", "h60_01", "hsocial"),
    "backoffice": ("h50_01", "h20_01", "h30_01", "h40_01", "hsocial"),
    "it_support": (),
}

INFRA_NODES = [
    ("c0", NETWORK_MODEL["infrastructure"]["c0"]["label"], "controller", NETWORK_MODEL["infrastructure"]["c0"].get("subtitle", "")),
    *(
        (name, switch["label"], "switch", switch.get("subtitle", ""))
        for name, switch in NETWORK_MODEL["switches"].items()
    ),
    *(
        (name, node["label"], node["type"], node.get("subtitle", ""))
        for name, node in NETWORK_MODEL["infrastructure"].items()
        if name != "c0"
    ),
]

ARCHITECTURE_LINKS = architecture_links(NETWORK_MODEL)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(command: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
        output = ((result.stdout or "") + (result.stderr or "")).strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return False, f"Không tìm thấy lệnh: {command[0]}"
    except subprocess.TimeoutExpired:
        return False, "Lệnh bị quá thời gian. Hãy kiểm tra Mininet/OVS có đang chạy không."


def topology_payload() -> dict[str, Any]:
    nodes = []
    groups = []
    hosts = sorted(ENGINE.hosts.values(), key=lambda item: (item["kind"] != "user", item["name"]))
    for name, group in ENGINE.groups.items():
        group_hosts = [host for host in hosts if host.get("group") == name and host.get("kind") == "user"]
        item = {
            "id": name,
            "label": group["label"],
            "type": "user_group",
            "site": group["site"],
            "vlan": int(group["vlan"]),
            "count": int(group["count"]),
            "subnet": group["subnet"],
            "switch": group["switch"],
            "hosts": group_hosts,
        }
        nodes.append(item)
        groups.append(item)

    nodes.extend(
        {"id": node_id, "label": label, "type": node_type, "subtitle": subtitle}
        for node_id, label, node_type, subtitle in INFRA_NODES
    )
    for service_name, service in ENGINE.services.items():
        if service_name != "h90":
            nodes.append(
                {
                    "id": service_name,
                    "label": service["label"],
                    "type": "blocked_service" if service_name == "hsocial" else "service",
                    "ip": service["ip"],
                }
            )
    nodes.append({"id": "h90", "label": ENGINE.services["h90"]["label"], "type": "service", "ip": ENGINE.services["h90"]["ip"]})

    links = [
        {
            "id": f"{source}-{target}",
            "source": source,
            "target": target,
            "type": link_type,
            "status": "up",
        }
        for source, target, link_type in ARCHITECTURE_LINKS
    ]
    return {
        "nodes": nodes,
        "groups": groups,
        "hosts": hosts,
        "links": links,
        "metadata": ENGINE.data["metadata"],
        "policy_map": policy_map_payload(),
        "summary": {
            "user_count": sum(int(group["count"]) for group in ENGINE.groups.values()),
            "service_count": len(ENGINE.services),
            "controlled_ovs_count": len(CONTROLLED_SWITCHES),
        },
    }


def representative_endpoint(node_id: str) -> str:
    if node_id in ENGINE.groups:
        group = ENGINE.groups[node_id]
        return f"{group['prefix']}_01"
    return node_id


def policy_map_payload() -> dict[str, Any]:
    selectable = [*ENGINE.groups.keys(), *ENGINE.services.keys()]
    names = {
        **{name: group["label"] for name, group in ENGINE.groups.items()},
        **{name: service["label"] for name, service in ENGINE.services.items()},
    }
    payload: dict[str, Any] = {}
    for source_id in selectable:
        source_endpoint = representative_endpoint(source_id)
        allow: list[str] = []
        deny: list[str] = []
        notes: dict[str, str] = {}
        for destination_id in selectable:
            if destination_id == source_id:
                continue
            destination_endpoint = representative_endpoint(destination_id)
            decision = policy_decision(source_endpoint, destination_endpoint)
            target_list = allow if decision["action"] == "allow" else deny
            target_list.append(destination_id)
            notes[destination_id] = decision["reason"]
        payload[source_id] = {
            "title": names.get(source_id, source_id),
            "allow": allow,
            "deny": deny,
            "notes": notes,
        }
    return payload


def policy_payload() -> dict[str, Any]:
    return {
        "metadata": ENGINE.data["metadata"],
        "host_groups": ENGINE.groups,
        "services": ENGINE.services,
        "policies": ENGINE.policies,
    }


def policy_decision(source: str, destination: str) -> dict[str, Any]:
    return ENGINE.decide(source, destination)


def host_pid(host: str) -> str | None:
    ok, output = run_command(["pgrep", "-f", f"mininet:{host}"], timeout=5)
    return output.splitlines()[-1].strip() if ok and output else None


def run_in_host(host: str, command: list[str], timeout: int = 20) -> tuple[bool, str]:
    pid = host_pid(host)
    if not pid:
        return False, f"Không tìm thấy namespace Mininet của {host}. Hãy chạy sdn_mpls_demo/run_topology.sh trước."
    base = ["mnexec", "-a", pid, *command]
    ok, output = run_command(base, timeout=timeout)
    if ok:
        return ok, output
    if "Operation not permitted" in output or "permission" in output.lower():
        sudo_ok, sudo_output = run_command(["sudo", "-n", *base], timeout=timeout)
        if sudo_ok:
            return sudo_ok, sudo_output
        return False, output + "\nBackend cần quyền truy cập namespace Mininet. Hãy chạy dashboard bằng sudo."
    return ok, output


def parse_ping(output: str) -> dict[str, Any]:
    result: dict[str, Any] = {"raw": output}
    summary = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received, ([0-9.]+)% packet loss", output)
    if summary:
        result.update(
            transmitted=int(summary.group(1)),
            received=int(summary.group(2)),
            packet_loss_percent=float(summary.group(3)),
        )
    rtt = re.search(r"= ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+) ms", output)
    if rtt:
        result.update(
            rtt_min_ms=float(rtt.group(1)),
            rtt_avg_ms=float(rtt.group(2)),
            rtt_max_ms=float(rtt.group(3)),
            jitter_ms=float(rtt.group(4)),
        )
    result["reachable"] = result.get("received", 0) > 0
    return result


def ping(source: str, destination: str, count: int = 3) -> dict[str, Any]:
    source_data = ENGINE.endpoint(source)
    destination_data = ENGINE.endpoint(destination)
    if not source_data or not destination_data:
        return {"ok": False, "message": "Nguồn hoặc đích không hợp lệ.", "raw": ""}
    decision = policy_decision(source, destination)
    ok, output = run_in_host(
        source,
        ["ping", "-c", str(count), "-W", "1", destination_data["ip"]],
        timeout=count + 7,
    )
    result = parse_ping(output)
    reachable = bool(result["reachable"])
    if not reachable and decision["action"] == "allow":
        decision = {
            **decision,
            "action": "deny",
            "blocked_at": decision["path"][-1] if decision["path"] else None,
            "reason": "Policy cho phép nhưng lab không nhận phản hồi. Hãy kiểm tra controller, flow và link Mininet.",
        }
    return {
        "ok": ok and reachable,
        "message": f"{source} → {destination}: {'PING THÀNH CÔNG' if reachable else 'PING THẤT BẠI'}",
        "decision": decision,
        "result": result,
        "raw": output,
    }


def parse_iperf3(output: str) -> dict[str, Any]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {"raw": output}
    end = payload.get("end", {})
    summary = end.get("sum_received") or end.get("sum") or {}
    return {
        "throughput_mbps": round(float(summary.get("bits_per_second", 0)) / 1_000_000, 3),
        "jitter_ms": summary.get("jitter_ms"),
        "packet_loss_percent": summary.get("lost_percent"),
        "raw": output,
    }


def iperf(source: str, destination: str, protocol: str = "tcp", seconds: int = 5) -> dict[str, Any]:
    destination_data = ENGINE.endpoint(destination)
    if not ENGINE.endpoint(source) or not destination_data:
        return {"ok": False, "message": "Nguồn hoặc đích không hợp lệ.", "raw": ""}
    decision = policy_decision(source, destination)
    if decision["action"] == "deny":
        return {"ok": False, "message": f"Không thể đo băng thông. {decision['reason']}", "decision": decision, "raw": ""}
    if not command_exists("iperf3"):
        return {"ok": False, "message": "Chưa cài iperf3. Chạy: sudo apt install -y iperf3", "raw": ""}

    run_in_host(destination, ["pkill", "-f", "iperf3 -s"], timeout=5)
    server_ok, server_output = run_in_host(
        destination,
        ["sh", "-lc", "iperf3 -s -1 >/tmp/dashboard_iperf3.log 2>&1 &"],
        timeout=5,
    )
    if not server_ok:
        return {"ok": False, "message": f"Không khởi động được iperf3 server trên {destination}.", "raw": server_output}
    time.sleep(0.4)
    command = ["iperf3", "-c", destination_data["ip"], "-t", str(seconds), "--json"]
    if protocol == "udp":
        command.extend(["-u", "-b", "20M"])
    ok, output = run_in_host(source, command, timeout=seconds + 15)
    result = parse_iperf3(output)
    return {
        "ok": ok,
        "message": f"{source} → {destination}: đã đo băng thông {protocol.upper()}",
        "decision": decision,
        "result": result,
        "raw": output,
    }


def estimate_voice_quality(rtt_ms: float, jitter_ms: float, packet_loss_percent: float) -> dict[str, Any]:
    effective_latency = (rtt_ms / 2) + (jitter_ms * 2) + 10
    r_factor = 93.2 - (effective_latency / 40 if effective_latency < 160 else (effective_latency - 120) / 10)
    r_factor = max(0.0, min(100.0, r_factor - packet_loss_percent * 2.5))
    mos = 1 + 0.035 * r_factor + 0.000007 * r_factor * (r_factor - 60) * (100 - r_factor)
    mos = round(max(1.0, min(4.5, mos)), 2)
    checks = {
        "latency": rtt_ms <= 150,
        "jitter": jitter_ms <= 30,
        "packet_loss": packet_loss_percent <= 1,
        "mos": mos >= 4.0,
    }
    passed = all(checks.values())
    return {
        "r_factor": round(r_factor, 1),
        "mos": mos,
        "rating": "Tốt - phù hợp cho cuộc gọi" if passed else "Cần theo dõi chất lượng cuộc gọi",
        "passed": passed,
        "checks": checks,
        "thresholds": {"rtt_ms": 150, "jitter_ms": 30, "packet_loss_percent": 1, "mos": 4.0},
    }


def call_quality(source: str, destination: str, seconds: int = 5) -> dict[str, Any]:
    decision = policy_decision(source, destination)
    if decision["action"] == "deny":
        return {"ok": False, "message": f"Không thể đo chất lượng. {decision['reason']}", "decision": decision, "raw": ""}
    ping_payload = ping(source, destination, count=10)
    if not ping_payload["ok"]:
        return ping_payload
    udp_payload = iperf(source, destination, protocol="udp", seconds=seconds)
    if not udp_payload["ok"]:
        return udp_payload
    ping_result = ping_payload["result"]
    udp_result = udp_payload["result"]
    rtt = float(ping_result.get("rtt_avg_ms") or 0)
    jitter = float(udp_result.get("jitter_ms") or ping_result.get("jitter_ms") or 0)
    loss = max(float(ping_result.get("packet_loss_percent") or 0), float(udp_result.get("packet_loss_percent") or 0))
    quality = estimate_voice_quality(rtt, jitter, loss)
    throughput = float(udp_result.get("throughput_mbps") or 0)
    quality["checks"]["throughput"] = throughput >= 0.1
    quality["passed"] = all(quality["checks"].values())
    result = {
        "rtt_avg_ms": rtt,
        "jitter_ms": jitter,
        "packet_loss_percent": loss,
        "throughput_mbps": throughput,
        **quality,
    }
    return {
        "ok": quality["passed"],
        "measurement_completed": True,
        "message": f"Đã đo chất lượng {source} → {destination}: {quality['rating']}.",
        "decision": decision,
        "result": result,
        "raw": f"=== PING ===\n{ping_payload['raw']}\n\n=== IPERF3 UDP ===\n{udp_payload['raw']}",
    }


def _case_result(name: str, category: str, expected: str, payload: dict[str, Any]) -> dict[str, Any]:
    reachable = bool(payload.get("result", {}).get("reachable", payload.get("ok", False)))
    passed = (expected == "allow" and bool(payload.get("ok"))) or (expected == "deny" and not reachable)
    metric = payload.get("result", {})
    return {
        "name": name,
        "category": category,
        "expected": expected,
        "passed": passed,
        "message": payload.get("message", ""),
        "reason": payload.get("decision", {}).get("reason", ""),
        "rtt_ms": metric.get("rtt_avg_ms"),
        "jitter_ms": metric.get("jitter_ms"),
        "loss_percent": metric.get("packet_loss_percent"),
        "mos": metric.get("mos"),
        "throughput_mbps": metric.get("throughput_mbps"),
        "raw": payload.get("raw", ""),
    }


def cluster_detail_test(cluster: str, seconds: int = 3) -> dict[str, Any]:
    if cluster not in CLUSTER_SOURCES:
        return {"ok": False, "message": f"Không có cụm test: {cluster}", "cases": []}

    source, label = CLUSTER_SOURCES[cluster]
    cases: list[dict[str, Any]] = []

    voice_payload = call_quality(source, "h90", seconds=seconds)
    cases.append(_case_result("Softphone Cfono/Gphone -> PBX/SBC/SIP-RTP", "voice", "allow", voice_payload))

    if "hcall" in CLUSTER_ALLOW_TARGETS[cluster]:
        cases.append(_case_result("Call App/CRM TCP throughput", "application", "allow", iperf(source, "hcall", "tcp", seconds)))
    if "hinternet" in CLUSTER_ALLOW_TARGETS[cluster]:
        cases.append(_case_result("Internet test reachability", "internet", "allow", ping(source, "hinternet", count=3)))
    if "hzalo" in CLUSTER_ALLOW_TARGETS[cluster]:
        cases.append(_case_result("Zalo service reachability", "internet", "allow", ping(source, "hzalo", count=3)))

    for target in CLUSTER_DENY_TARGETS[cluster]:
        cases.append(_case_result(f"Policy chặn {source} -> {target}", "segmentation", "deny", ping(source, target, count=2)))

    passed = sum(1 for item in cases if item["passed"])
    total = len(cases)
    score = round((passed / total) * 100, 1) if total else 0
    critical_failures = [
        item for item in cases
        if not item["passed"] and item["category"] in {"voice", "segmentation"}
    ]
    verdict = (
        "Đạt cho demo vận hành" if not critical_failures and score >= 80
        else "Chưa đạt: cần kiểm tra voice hoặc segmentation"
    )
    return {
        "ok": not critical_failures and score >= 80,
        "cluster": cluster,
        "source": source,
        "label": label,
        "score": score,
        "passed": passed,
        "total": total,
        "message": f"{label}: {verdict} ({passed}/{total}, {score}%).",
        "cases": cases,
        "verdict": verdict,
        "softphone_note": (
            "Cfono/Gphone là softphone cài trên máy agent: lab chỉ cho user VLAN đi tới "
            "cụm PBX/SBC/SIP-RTP và Call App cần thiết. Không mở ping ngang giữa "
            "Project/Telesale/BackOffice; chỉ IT Support có quyền remote/support có kiểm soát."
        ),
    }


def parse_flow_line(line: str, switch: str) -> dict[str, Any] | None:
    if "OFPST" in line or "NXST" in line:
        return None
    src_ip = re.search(r"nw_src=([0-9.]+)", line)
    dst_ip = re.search(r"nw_dst=([0-9.]+)", line)
    priority = re.search(r"priority=(\d+)", line)
    packets = re.search(r"n_packets=(\d+)", line)
    byte_count = re.search(r"n_bytes=(\d+)", line)
    actions = line.split("actions=", 1)[1] if "actions=" in line else ""
    source = ENGINE.endpoint_by_ip(src_ip.group(1))["name"] if src_ip and ENGINE.endpoint_by_ip(src_ip.group(1)) else "*"
    destination = ENGINE.endpoint_by_ip(dst_ip.group(1))["name"] if dst_ip and ENGINE.endpoint_by_ip(dst_ip.group(1)) else "*"
    action = "DROP" if actions in {"", "drop"} else ("PACKET_IN" if "CONTROLLER" in actions else "ALLOW")
    reason = "Table-miss gửi gói mới lên controller."
    if source != "*" and destination != "*":
        decision = policy_decision(source, destination)
        reason = decision["reason"] if action != "DROP" or decision["action"] == "deny" else "Flow chặn tạm thời do người vận hành cài."
    return {
        "switch": switch,
        "source": source,
        "destination": destination,
        "src": source,
        "dst": destination,
        "action": action,
        "priority": int(priority.group(1)) if priority else 0,
        "match": f"{source} → {destination}",
        "raw_match": line.split("actions=", 1)[0].strip(),
        "raw_action": actions or "drop",
        "packets": int(packets.group(1)) if packets else 0,
        "bytes": int(byte_count.group(1)) if byte_count else 0,
        "reason": reason,
        "explanation": reason,
        "logical_device": switch,
    }


def ovs_flows() -> dict[str, Any]:
    flows = []
    raw_outputs = []
    live_switches = []
    for switch in CONTROLLED_SWITCHES:
        ok, output = run_command(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", switch], timeout=8)
        if not ok:
            continue
        live_switches.append(switch)
        raw_outputs.append(f"=== {switch} ===\n{output}")
        flows.extend(
            flow
            for line in output.splitlines()
            if (flow := parse_flow_line(line, switch)) is not None
        )
    if RUNTIME_FLOWS_FILE.exists():
        try:
            controller_flows = json.loads(RUNTIME_FLOWS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            controller_flows = []
    else:
        controller_flows = []
    return {
        "ok": bool(live_switches),
        "flows": flows,
        "controller_flows": controller_flows[-200:],
        "switches": live_switches,
        "raw": "\n\n".join(raw_outputs),
    }


def current_metrics() -> dict[str, Any]:
    payload = ovs_flows()
    return {
        "timestamp": now_iso(),
        "live": payload["ok"],
        "switches": payload["switches"],
        "flow_count": len(payload["flows"]),
        "packets": sum(flow["packets"] for flow in payload["flows"]),
        "bytes": sum(flow["bytes"] for flow in payload["flows"]),
        "flows": payload["flows"],
    }


def pair_flow_bytes(source: str, destination: str) -> int:
    payload = ovs_flows()
    total = 0
    for flow in payload["flows"]:
        if (
            (flow.get("source") == source and flow.get("destination") == destination)
            or (flow.get("source") == destination and flow.get("destination") == source)
        ):
            total += int(flow.get("bytes") or 0)
    return total


def pair_realtime_metrics(
    source: str,
    destination: str,
    previous_bytes: int | None = None,
    previous_time: float | None = None,
) -> dict[str, Any]:
    timestamp = time.time()
    ping_payload = ping(source, destination, count=2)
    result = ping_payload.get("result", {})
    byte_count = pair_flow_bytes(source, destination)
    throughput_mbps = 0.0
    if previous_bytes is not None and previous_time is not None and timestamp > previous_time:
        delta_bytes = max(0, byte_count - previous_bytes)
        throughput_mbps = round((delta_bytes * 8) / (timestamp - previous_time) / 1_000_000, 4)
    return {
        "timestamp": now_iso(),
        "source": source,
        "destination": destination,
        "ok": bool(ping_payload.get("ok")),
        "delay_ms": result.get("rtt_avg_ms"),
        "packet_loss_percent": result.get("packet_loss_percent"),
        "jitter_ms": result.get("jitter_ms"),
        "throughput_mbps": throughput_mbps,
        "byte_count": byte_count,
        "previous_byte_count": previous_bytes,
        "message": ping_payload.get("message"),
        "decision": ping_payload.get("decision"),
    }


def temporary_block(source: str, destination: str, block: bool) -> dict[str, Any]:
    source_data = ENGINE.endpoint(source)
    destination_data = ENGINE.endpoint(destination)
    if not source_data or not destination_data:
        return {"ok": False, "message": "Nguồn hoặc đích không hợp lệ.", "raw": ""}
    outputs = []
    success = True
    for switch in CONTROLLED_SWITCHES:
        exists, _ = run_command(["ovs-vsctl", "br-exists", switch], timeout=4)
        if not exists:
            continue
        for src_ip, dst_ip in ((source_data["ip"], destination_data["ip"]), (destination_data["ip"], source_data["ip"])):
            match = f"ip,nw_src={src_ip},nw_dst={dst_ip}"
            command = ["ovs-ofctl", "-O", "OpenFlow13", "add-flow", switch, f"priority=500,{match},actions=drop"]
            if not block:
                command = ["ovs-ofctl", "-O", "OpenFlow13", "del-flows", switch, match]
            ok, output = run_command(command, timeout=8)
            success = success and ok
            outputs.append(output)
    verb = "chặn" if block else "gỡ chặn"
    return {"ok": success, "message": f"Đã {verb} tạm thời {source} ↔ {destination} trên các OVS đang hoạt động.", "raw": "\n".join(outputs)}


def live_status() -> dict[str, Any]:
    bridges = {}
    for switch in CONTROLLED_SWITCHES:
        bridges[switch] = run_command(["ovs-vsctl", "br-exists", switch], timeout=3)[0]
    ok, process_list = run_command(["pgrep", "-af", "mininet:"], timeout=5)
    hosts = {
        name: bool(ok and re.search(rf"mininet:{re.escape(name)}(?:\s|$)", process_list))
        for name in ENGINE.hosts
    }
    return {
        "ovs_bridge": any(bridges.values()),
        "bridges": bridges,
        "mnexec": command_exists("mnexec"),
        "iperf3": command_exists("iperf3"),
        "hosts": hosts,
        "user_hosts_online": sum(hosts[name] for name, data in ENGINE.hosts.items() if data["kind"] == "user"),
    }
