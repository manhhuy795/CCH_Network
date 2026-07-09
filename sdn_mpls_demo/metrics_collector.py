#!/usr/bin/env python3
"""Thu thập ping, iperf3 và flow counter từ lab Mininet đang chạy."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time


def run(command, timeout=30):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    return result.returncode == 0, ((result.stdout or "") + (result.stderr or "")).strip()


def host_pid(host):
    ok, output = run(["pgrep", "-f", f"mininet:{host}"], timeout=5)
    return output.splitlines()[-1] if ok and output else None


def in_host(host, command, timeout=30):
    pid = host_pid(host)
    if not pid:
        return False, f"Không tìm thấy host {host}. Hãy chạy topology trước."
    return run(["mnexec", "-a", pid, *command], timeout=timeout)


def host_ip(host):
    ok, output = in_host(host, ["hostname", "-I"], timeout=5)
    if not ok or not output:
        raise RuntimeError(f"Không đọc được IP của {host}: {output}")
    addresses = [item for item in output.split() if item.startswith("172.16.")]
    if not addresses:
        raise RuntimeError(f"Host {host} không có địa chỉ 172.16.x.x.")
    return addresses[0]


def ping(source, destination, count):
    destination_ip = host_ip(destination)
    ok, output = in_host(source, ["ping", "-c", str(count), "-W", "1", destination_ip], timeout=count + 8)
    loss = re.search(r"([0-9.]+)% packet loss", output)
    rtt = re.search(r"= ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+) ms", output)
    return {
        "ok": ok,
        "source": source,
        "destination": destination,
        "packet_loss_percent": float(loss.group(1)) if loss else 100.0,
        "rtt_avg_ms": float(rtt.group(2)) if rtt else None,
        "raw": output,
    }


def iperf3(source, destination, protocol, seconds):
    destination_ip = host_ip(destination)
    in_host(destination, ["pkill", "-f", "iperf3 -s"], timeout=5)
    server_ok, server_output = in_host(
        destination,
        ["sh", "-lc", "iperf3 -s -1 >/tmp/iperf3_server.log 2>&1 &"],
        timeout=5,
    )
    if not server_ok:
        return {"ok": False, "message": "Không khởi động được iperf3 server.", "raw": server_output}
    time.sleep(0.4)
    command = ["iperf3", "-c", destination_ip, "-t", str(seconds), "--json"]
    if protocol == "udp":
        command.extend(["-u", "-b", "20M"])
    ok, output = in_host(source, command, timeout=seconds + 15)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return {"ok": False, "message": "Không phân tích được kết quả iperf3.", "raw": output}
    end = payload.get("end", {})
    summary = end.get("sum_received") or end.get("sum") or {}
    return {
        "ok": ok,
        "source": source,
        "destination": destination,
        "protocol": protocol,
        "throughput_mbps": round(float(summary.get("bits_per_second", 0)) / 1_000_000, 3),
        "jitter_ms": summary.get("jitter_ms"),
        "packet_loss_percent": summary.get("lost_percent"),
        "raw": output,
    }


def main():
    parser = argparse.ArgumentParser(description="Đo kiểm lab Hybrid MPLS + SDN")
    parser.add_argument("mode", choices=["ping", "tcp", "udp", "flows"])
    parser.add_argument("--source", default="h20_01")
    parser.add_argument("--destination", default="h90")
    parser.add_argument("--seconds", type=int, default=5)
    args = parser.parse_args()

    if args.mode == "ping":
        result = ping(args.source, args.destination, count=5)
    elif args.mode in {"tcp", "udp"}:
        result = iperf3(args.source, args.destination, args.mode, args.seconds)
    else:
        ok, output = run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "core_hq"])
        result = {"ok": ok, "raw": output}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
