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
from sdn_mpls_demo.policy_engine import GROUP_PATHS, PolicyEngine


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_FILE = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
RUNTIME_FLOWS_FILE = REPO_ROOT / "sdn_mpls_demo" / "runtime" / "installed_flows.json"
CONTROLLED_SWITCHES = (
    "access_hq_a",
    "access_hq_b",
    "access_hq_c",
    "voice_mgmt",
    "core_hq",
    "access_branch",
    "dist_branch",
)

ENGINE = PolicyEngine(POLICY_FILE)

INFRA_NODES = [
    ("c0", "SDN Controller", "controller"),
    ("access_hq_a", "Access HQ-A", "switch"),
    ("access_hq_b", "Access HQ-B", "switch"),
    ("access_hq_c", "Access HQ-C", "switch"),
    ("voice_mgmt", "Voice Access", "switch"),
    ("core_hq", "HQ Core SDN", "switch"),
    ("access_branch", "Branch Access", "switch"),
    ("dist_branch", "Branch Distribution", "switch"),
    ("ce_hq", "CE Router HQ", "router"),
    ("mpls_cloud", "MPLS L3VPN Cloud", "wan"),
    ("ce_branch", "CE Router Branch", "router"),
    ("fw_hq", "Firewall HQ", "firewall"),
    ("fw_branch", "Firewall Branch", "firewall"),
    ("internet", "Internet Zone", "service_edge"),
]

ARCHITECTURE_LINKS = [
    ("project_a", "access_hq_a", "data"),
    ("project_b", "access_hq_b", "data"),
    ("project_c", "access_hq_c", "data"),
    ("h90", "voice_mgmt", "data"),
    ("access_hq_a", "core_hq", "data"),
    ("access_hq_b", "core_hq", "data"),
    ("access_hq_c", "core_hq", "data"),
    ("voice_mgmt", "core_hq", "data"),
    ("telesale", "access_branch", "data"),
    ("backoffice", "access_branch", "data"),
    ("access_branch", "dist_branch", "data"),
    ("core_hq", "ce_hq", "mpls"),
    ("ce_hq", "mpls_cloud", "mpls"),
    ("mpls_cloud", "ce_branch", "mpls"),
    ("ce_branch", "dist_branch", "mpls"),
    ("core_hq", "fw_hq", "data"),
    ("fw_hq", "internet", "data"),
    ("dist_branch", "fw_branch", "data"),
    ("fw_branch", "internet", "data"),
    ("internet", "hzalo", "data"),
    ("internet", "hcall", "data"),
    ("internet", "hsocial", "data"),
    ("internet", "hinternet", "data"),
]


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
    for name, group in ENGINE.groups.items():
        item = {
            "id": name,
            "label": group["label"],
            "type": "user_group",
            "site": group["site"],
            "vlan": int(group["vlan"]),
            "count": int(group["count"]),
            "subnet": group["subnet"],
            "switch": group["switch"],
        }
        nodes.append(item)
        groups.append(item)

    nodes.extend({"id": node_id, "label": label, "type": node_type} for node_id, label, node_type in INFRA_NODES)
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
    nodes.append({"id": "h90", "label": "Voice Service", "type": "service", "ip": ENGINE.services["h90"]["ip"]})

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
    hosts = sorted(ENGINE.hosts.values(), key=lambda item: (item["kind"] != "user", item["name"]))
    return {
        "nodes": nodes,
        "groups": groups,
        "hosts": hosts,
        "links": links,
        "metadata": ENGINE.data["metadata"],
        "summary": {"user_count": 100, "service_count": 5, "controlled_ovs_count": 7},
    }


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
