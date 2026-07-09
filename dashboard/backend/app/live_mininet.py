from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
POLICY_FILE = REPO_ROOT / "sdn_demo" / "policy.yml"
BRIDGE = "s1"

HOST_LABELS = {
    "h20": "Dự án A - VLAN 20 - Trụ sở",
    "h30": "Dự án B - VLAN 30 - Trụ sở",
    "h40": "Dự án C - VLAN 40 - Trụ sở",
    "h50": "Telesale - VLAN 50 - Chi nhánh",
    "h60": "Backoffice - VLAN 60 - Chi nhánh",
    "h90": "Dịch vụ thoại - VLAN 90",
    "hzalo": "Dịch vụ Zalo - Internet",
    "hcall": "Ứng dụng Call Center - Internet",
    "hsocial": "Mạng xã hội - Bị chặn",
}

LOGICAL_PATHS = {
    "h20": ["h20", "access_hq_a", "core_hq"],
    "h30": ["h30", "access_hq_b", "core_hq"],
    "h40": ["h40", "access_hq_c", "core_hq"],
    "h50": ["h50", "access_branch", "dist_branch"],
    "h60": ["h60", "access_branch", "dist_branch"],
    "h90": ["h90", "voice_mgmt", "core_hq"],
    "hzalo": ["internet", "hzalo"],
    "hcall": ["internet", "hcall"],
    "hsocial": ["internet", "hsocial"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_policy() -> dict[str, Any]:
    with POLICY_FILE.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


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
    policy = load_policy()
    nodes = [
        {"id": "c0", "label": "SDN Controller", "type": "controller", "ip": "127.0.0.1:6653"},
        {"id": BRIDGE, "label": "OVS Dataplane Switch", "type": "switch", "ip": "OpenFlow13"},
    ]
    links = [{"id": f"c0-{BRIDGE}", "source": "c0", "target": BRIDGE, "status": "up"}]

    for host, data in policy["hosts"].items():
        nodes.append(
            {
                "id": host,
                "label": HOST_LABELS.get(host, data.get("role", host)),
                "type": data.get("role", "host"),
                "site": data.get("site", ""),
                "ip": data["ip"],
                "port": data["switch_port"],
            }
        )
        links.append(
            {
                "id": f"{BRIDGE}-{host}",
                "source": BRIDGE,
                "target": host,
                "status": "up",
                "port": data["switch_port"],
            }
        )

    return {"nodes": nodes, "links": links, "metadata": policy.get("metadata", {})}


def policy_payload() -> dict[str, Any]:
    policy = load_policy()
    deny_pairs = {tuple(pair) for pair in policy.get("deny_pairs", [])}
    policies = {
        "isolate_hq_projects": all(pair in deny_pairs for pair in [("h20", "h30"), ("h20", "h40"), ("h30", "h40")]),
        "isolate_branch_vlan_50_60": ("h50", "h60") in deny_pairs,
        "allow_voice": bool(policy.get("voice_enabled")),
        "allow_zalo": "hzalo" in policy.get("allowed_services", []),
        "allow_call_app": "hcall" in policy.get("allowed_services", []),
        "block_social_media": "hsocial" in policy.get("blocked_services", []),
    }
    return {"metadata": policy.get("metadata", {}), "hosts": policy["hosts"], "policies": policies}


def logical_path(source: str, destination: str) -> list[str]:
    left = LOGICAL_PATHS.get(source, [source])
    right = LOGICAL_PATHS.get(destination, [destination])
    src_site = "branch" if source in {"h50", "h60"} else "hq"

    if source in {"h20", "h30", "h40"} and destination in {"h20", "h30", "h40"}:
        return [*left, *list(reversed(right[:-1]))]

    if source in {"h50", "h60"} and destination in {"h50", "h60"}:
        return [source, "access_branch", destination]

    if destination == "h90" or source == "h90":
        if source == "h90":
            return list(reversed(logical_path(destination, source)))
        if source in {"h50", "h60"}:
            return [*left, "wan", "core_hq", "voice_mgmt", "h90"]
        return [*left, "voice_mgmt", "h90"] if "voice_mgmt" not in left else [*left, "h90"]

    if destination in {"hzalo", "hcall", "hsocial"}:
        edge = ["fw_branch", "policy_branch"] if src_site == "branch" else ["fw_hq", "policy_hq"]
        return [*left, *edge, "internet", destination]

    if source in {"hzalo", "hcall", "hsocial"}:
        return list(reversed(logical_path(destination, source)))

    if src_site == "branch":
        return [*left, "dist_branch"]
    return [*left, "core_hq"]


def policy_decision(source: str, destination: str) -> dict[str, Any]:
    policy = load_policy()
    hosts = policy["hosts"]
    if source not in hosts or destination not in hosts:
        return {
            "action": "deny",
            "reason": "Không tìm thấy nguồn hoặc đích trong chính sách.",
            "path": [],
            "expected_reachable": False,
            "blocked_at": None,
        }

    deny_pairs = {tuple(pair) for pair in policy.get("deny_pairs", [])}
    pair = (source, destination)
    reverse_pair = (destination, source)
    path = logical_path(source, destination)

    if pair in deny_pairs or reverse_pair in deny_pairs:
        return {
            "action": "deny",
            "reason": "Bị chặn bởi chính sách cách ly giữa các VLAN/dự án.",
            "path": path,
            "expected_reachable": False,
            "blocked_at": destination,
        }

    blocked_services = set(policy.get("blocked_services", []))
    clients = set(policy.get("client_hosts", []))
    if (destination in blocked_services and source in clients) or (source in blocked_services and destination in clients):
        return {
            "action": "deny",
            "reason": "Bị chặn tại chính sách Internet Security: không cho phép mạng xã hội.",
            "path": path,
            "expected_reachable": False,
            "blocked_at": path[-2] if len(path) > 1 else destination,
        }

    if policy.get("voice_enabled") and (source == policy.get("voice_service") or destination == policy.get("voice_service")):
        return {
            "action": "allow",
            "reason": "Dịch vụ thoại đang bật: người dùng được phép truy cập Voice Service.",
            "path": path,
            "expected_reachable": True,
            "blocked_at": None,
        }

    allowed_services = set(policy.get("allowed_services", []))
    if (destination in allowed_services and source in clients) or (source in allowed_services and destination in clients):
        service = destination if destination in allowed_services else source
        return {
            "action": "allow",
            "reason": f"Chính sách cho phép truy cập dịch vụ {service}.",
            "path": path,
            "expected_reachable": True,
            "blocked_at": None,
        }

    return {
        "action": "deny",
        "reason": "Bị chặn bởi quy tắc mặc định từ chối của SDN.",
        "path": path,
        "expected_reachable": False,
        "blocked_at": destination,
    }


def host_pid(host: str) -> str | None:
    ok, output = run_command(["pgrep", "-f", f"mininet:{host}"], timeout=5)
    if not ok or not output:
        return None
    return output.splitlines()[-1].strip()


def run_in_host(host: str, command: list[str], timeout: int = 20) -> tuple[bool, str]:
    pid = host_pid(host)
    if not pid:
        return False, f"Không tìm thấy namespace Mininet của host {host}. Hãy chạy ./sdn_demo/run_demo.sh trước."

    base = ["mnexec", "-a", pid, *command]
    ok, output = run_command(base, timeout=timeout)
    if ok:
        return ok, output

    if "Operation not permitted" in output or "permission" in output.lower():
        sudo_ok, sudo_output = run_command(["sudo", "-n", *base], timeout=timeout)
        if sudo_ok:
            return sudo_ok, sudo_output
        return (
            False,
            output
            + "\n\nBackend cần quyền truy cập namespace Mininet. Hãy chạy dashboard bằng sudo:\n"
            + "sudo -E .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000",
        )
    return ok, output


def parse_ping(output: str) -> dict[str, Any]:
    result: dict[str, Any] = {"raw": output}
    match = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received, ([0-9.]+)% packet loss", output)
    if match:
        result.update(
            {
                "transmitted": int(match.group(1)),
                "received": int(match.group(2)),
                "packet_loss_percent": float(match.group(3)),
            }
        )
    rtt = re.search(r"rtt min/avg/max/(?:mdev|stddev) = ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+) ms", output)
    if rtt:
        result.update({"rtt_min_ms": float(rtt.group(1)), "rtt_avg_ms": float(rtt.group(2)), "rtt_max_ms": float(rtt.group(3))})
    result["reachable"] = result.get("received", 0) > 0
    return result


def ping(source: str, destination: str, count: int = 3) -> dict[str, Any]:
    policy = load_policy()
    if source not in policy["hosts"] or destination not in policy["hosts"]:
        return {"ok": False, "message": "Nguồn hoặc đích không hợp lệ.", "raw": ""}
    decision = policy_decision(source, destination)
    dst_ip = policy["hosts"][destination]["ip"]
    ok, output = run_in_host(source, ["ping", "-c", str(count), "-W", "1", dst_ip], timeout=count + 5)
    parsed = parse_ping(output)
    reachable = bool(parsed.get("reachable"))
    if not reachable and decision["action"] == "allow":
        decision = {
            **decision,
            "action": "deny",
            "reason": (
                "Chính sách gốc cho phép nhưng gói tin không nhận được phản hồi. "
                "Hãy kiểm tra flow chặn tạm thời, trạng thái host và liên kết Mininet."
            ),
            "blocked_at": destination,
        }
    message = f"{source} → {destination}: {'PING THÀNH CÔNG' if reachable else 'PING THẤT BẠI'}"
    if not reachable:
        message += f" | Lý do: {decision['reason']}"
    return {
        "ok": ok and reachable,
        "message": message,
        "decision": decision,
        "result": parsed,
        "raw": output,
    }


def parse_iperf(output: str) -> dict[str, Any]:
    values = re.findall(r"([0-9.]+)\s+([KMG])bits/sec", output)
    result: dict[str, Any] = {"raw": output}
    if values:
        value, unit = values[-1]
        multiplier = {"K": 0.001, "M": 1.0, "G": 1000.0}[unit]
        result["throughput_mbps"] = round(float(value) * multiplier, 3)
    udp_summary = re.findall(
        r"([0-9.]+)\s+ms\s+\d+\s*/\s*\d+\s+\(([0-9.]+)%\)",
        output,
    )
    if udp_summary:
        result["jitter_ms"] = float(udp_summary[-1][0])
        result["packet_loss_percent"] = float(udp_summary[-1][1])
    return result


def iperf(source: str, destination: str, protocol: str = "tcp", seconds: int = 5) -> dict[str, Any]:
    policy = load_policy()
    if source not in policy["hosts"] or destination not in policy["hosts"]:
        return {"ok": False, "message": "Nguồn hoặc đích không hợp lệ.", "raw": ""}
    decision = policy_decision(source, destination)
    if decision["action"] == "deny":
        return {"ok": False, "message": f"Không thể đo băng thông. {decision['reason']}", "decision": decision, "raw": ""}
    if not command_exists("iperf"):
        return {"ok": False, "message": "Chưa cài iperf. Chạy: sudo apt install -y iperf", "raw": ""}

    dst_ip = policy["hosts"][destination]["ip"]
    run_in_host(destination, ["sh", "-lc", "pkill -f 'iperf -s -p 5001' >/dev/null 2>&1 || true"], timeout=5)
    server_cmd = "iperf -s -p 5001 >/tmp/sdn_dashboard_iperf.log 2>&1 &"
    if protocol == "udp":
        server_cmd = "iperf -s -u -p 5001 >/tmp/sdn_dashboard_iperf.log 2>&1 &"
    server_ok, server_output = run_in_host(destination, ["sh", "-lc", server_cmd], timeout=5)
    if not server_ok:
        return {"ok": False, "message": f"Không khởi động được iperf server trên {destination}.", "raw": server_output}

    client_cmd = ["iperf", "-c", dst_ip, "-p", "5001", "-t", str(seconds), "-i", "1"]
    if protocol == "udp":
        client_cmd.extend(["-u", "-b", "20M"])
    ok, output = run_in_host(source, client_cmd, timeout=seconds + 10)
    run_in_host(destination, ["sh", "-lc", "pkill -f 'iperf -s -p 5001' >/dev/null 2>&1 || true"], timeout=5)
    parsed = parse_iperf(output)
    message = f"{source} → {destination}: đã đo băng thông {protocol.upper()}"
    return {"ok": ok, "message": message, "decision": decision, "result": parsed, "raw": output}


def estimate_voice_quality(rtt_ms: float, jitter_ms: float, packet_loss_percent: float) -> dict[str, Any]:
    """Ước lượng E-model đơn giản từ số đo mạng thật, phù hợp mục đích lab."""
    effective_latency = (rtt_ms / 2) + (jitter_ms * 2) + 10
    if effective_latency < 160:
        r_factor = 93.2 - (effective_latency / 40)
    else:
        r_factor = 93.2 - ((effective_latency - 120) / 10)
    r_factor = max(0.0, min(100.0, r_factor - (packet_loss_percent * 2.5)))
    mos = 1 + (0.035 * r_factor) + (
        0.000007 * r_factor * (r_factor - 60) * (100 - r_factor)
    )
    mos = round(max(1.0, min(4.5, mos)), 2)

    checks = {
        "latency": rtt_ms <= 150,
        "jitter": jitter_ms <= 30,
        "packet_loss": packet_loss_percent <= 1,
        "mos": mos >= 4.0,
    }
    passed = all(checks.values())
    if passed:
        rating = "Tốt - phù hợp cho cuộc gọi"
    elif mos >= 3.6 and packet_loss_percent <= 3:
        rating = "Chấp nhận được - cần theo dõi"
    else:
        rating = "Kém - có nguy cơ ảnh hưởng cuộc gọi"
    return {
        "r_factor": round(r_factor, 1),
        "mos": mos,
        "rating": rating,
        "passed": passed,
        "checks": checks,
        "thresholds": {
            "rtt_ms": 150,
            "jitter_ms": 30,
            "packet_loss_percent": 1,
            "mos": 4.0,
        },
    }


def call_quality(source: str, destination: str, seconds: int = 5) -> dict[str, Any]:
    decision = policy_decision(source, destination)
    if decision["action"] == "deny":
        return {
            "ok": False,
            "message": f"Không thể đo chất lượng cuộc gọi. {decision['reason']}",
            "decision": decision,
            "raw": "",
        }

    ping_payload = ping(source, destination, count=10)
    if not ping_payload["ok"]:
        return {
            "ok": False,
            "message": "Bài đo thất bại vì đích không phản hồi ping.",
            "decision": decision,
            "result": ping_payload.get("result", {}),
            "raw": ping_payload.get("raw", ""),
        }

    udp_payload = iperf(source, destination, protocol="udp", seconds=seconds)
    if not udp_payload["ok"]:
        return udp_payload

    ping_result = ping_payload.get("result", {})
    udp_result = udp_payload.get("result", {})
    rtt_ms = float(ping_result.get("rtt_avg_ms", 0))
    jitter_ms = float(udp_result.get("jitter_ms", 0))
    throughput_mbps = float(udp_result.get("throughput_mbps", 0))
    loss = max(
        float(ping_result.get("packet_loss_percent", 0)),
        float(udp_result.get("packet_loss_percent", 0)),
    )
    quality = estimate_voice_quality(rtt_ms, jitter_ms, loss)
    quality["checks"]["throughput"] = throughput_mbps >= 0.1
    quality["thresholds"]["throughput_mbps"] = 0.1
    quality["passed"] = all(quality["checks"].values())
    if not quality["checks"]["throughput"]:
        quality["rating"] = "Kém - thông lượng không đủ cho luồng thoại"
    result = {
        "rtt_avg_ms": rtt_ms,
        "jitter_ms": jitter_ms,
        "packet_loss_percent": loss,
        "throughput_mbps": throughput_mbps,
        **quality,
    }
    return {
        "ok": quality["passed"],
        "measurement_completed": True,
        "message": f"Đã đo chất lượng cuộc gọi {source} → {destination}: {quality['rating']}.",
        "decision": decision,
        "result": result,
        "raw": f"=== PING ===\n{ping_payload['raw']}\n\n=== IPERF UDP ===\n{udp_payload['raw']}",
    }


def parse_flow_line(line: str, host_by_ip: dict[str, str]) -> dict[str, Any] | None:
    if "NXST" in line or "OFPST" in line:
        return None
    src_ip = re.search(r"nw_src=([0-9.]+)", line)
    dst_ip = re.search(r"nw_dst=([0-9.]+)", line)
    priority = re.search(r"priority=(\d+)", line)
    packets = re.search(r"n_packets=(\d+)", line)
    byte_count = re.search(r"n_bytes=(\d+)", line)
    actions = line.split("actions=", 1)[1] if "actions=" in line else ""
    output = re.search(r"output:(\d+)", actions)

    action = "DROP" if actions == "drop" or actions == "" else "ALLOW"
    src = host_by_ip.get(src_ip.group(1), src_ip.group(1)) if src_ip else "*"
    dst = host_by_ip.get(dst_ip.group(1), dst_ip.group(1)) if dst_ip else "*"
    output_port = output.group(1) if output else "DROP"
    if action == "DROP":
        explanation = f"Chặn lưu lượng {src} → {dst}"
    elif src == "*" and dst == "*":
        explanation = "Table-miss: gửi gói đầu tiên lên controller"
    else:
        explanation = f"Cho phép {src} → {dst}, chuyển ra cổng {output_port}"

    return {
        "switch": BRIDGE,
        "src": src,
        "dst": dst,
        "action": action,
        "priority": int(priority.group(1)) if priority else 0,
        "output_port": output_port,
        "packets": int(packets.group(1)) if packets else 0,
        "bytes": int(byte_count.group(1)) if byte_count else 0,
        "explanation": explanation,
        "match": f"{src} -> {dst}",
        "reason": actions or "table miss/drop",
        "raw": line,
    }


def ovs_flows() -> dict[str, Any]:
    policy = load_policy()
    host_by_ip = {data["ip"]: host for host, data in policy["hosts"].items()}
    ok, output = run_command(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", BRIDGE], timeout=10)
    flows = []
    if ok:
        flows = [flow for line in output.splitlines() if (flow := parse_flow_line(line, host_by_ip))]
    return {"ok": ok, "flows": flows, "raw": output}


def ovs_ports_raw() -> tuple[bool, str]:
    return run_command(["ovs-ofctl", "-O", "OpenFlow13", "dump-ports", BRIDGE], timeout=10)


def current_metrics() -> dict[str, Any]:
    flow_payload = ovs_flows()
    ok, ports = ovs_ports_raw()
    total_packets = sum(flow.get("packets", 0) for flow in flow_payload["flows"])
    total_bytes = sum(flow.get("bytes", 0) for flow in flow_payload["flows"])
    return {
        "timestamp": now_iso(),
        "live": flow_payload["ok"] and ok,
        "links": [
            {
                "id": "ovs-live-counters",
                "throughput_mbps": 0,
                "delay_ms": None,
                "packet_loss_percent": None,
                "jitter_ms": None,
                "status": "up" if ok else "down",
                "packets": total_packets,
                "bytes": total_bytes,
            }
        ],
        "flows": flow_payload["flows"],
        "ports_raw": ports,
    }


def temporary_block(source: str, destination: str, block: bool) -> dict[str, Any]:
    policy = load_policy()
    if source not in policy["hosts"] or destination not in policy["hosts"]:
        return {"ok": False, "message": "Nguồn hoặc đích không hợp lệ.", "raw": ""}
    pairs = [
        (policy["hosts"][source]["ip"], policy["hosts"][destination]["ip"]),
        (policy["hosts"][destination]["ip"], policy["hosts"][source]["ip"]),
    ]
    outputs = []
    ok_all = True
    for src_ip, dst_ip in pairs:
        match = f"ip,nw_src={src_ip},nw_dst={dst_ip}"
        if block:
            ok, output = run_command(["ovs-ofctl", "-O", "OpenFlow13", "add-flow", BRIDGE, f"priority=500,{match},actions=drop"], timeout=10)
        else:
            ok, output = run_command(["ovs-ofctl", "-O", "OpenFlow13", "del-flows", BRIDGE, match], timeout=10)
        ok_all = ok_all and ok
        outputs.append(output)
    action = "chặn" if block else "gỡ chặn"
    return {"ok": ok_all, "message": f"Đã {action} tạm thời {source} ↔ {destination} bằng OpenFlow.", "raw": "\n".join(outputs)}


def live_status() -> dict[str, Any]:
    ovs_ok, ovs_output = run_command(["ovs-vsctl", "br-exists", BRIDGE], timeout=5)
    policy = load_policy()
    host_pids = {host: host_pid(host) for host in policy["hosts"]}
    return {
        "ovs_bridge": ovs_ok,
        "ovs_message": ovs_output,
        "mnexec": command_exists("mnexec"),
        "iperf": command_exists("iperf"),
        "hosts": {host: bool(pid) for host, pid in host_pids.items()},
    }
