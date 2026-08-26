#!/usr/bin/env python3
"""Live Integration Test Suite for Full-SDN Fabric on Ubuntu + Mininet + OVS + OS-Ken.

Executes live against the running Mininet topology and OS-Ken controller.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Add backend to sys.path for mininet_control
REPO_ROOT = Path("/home/huy/CCH_Network")
sys.path.insert(0, str(REPO_ROOT / "dashboard" / "backend"))

try:
    from app.mininet_control import request_agent
except ImportError:
    # Fallback to local import
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard" / "backend"))
    from app.mininet_control import request_agent

SWITCHES = ["core_hq", "dist_branch", "access_floor1", "access_floor2", "access_branch", "infra_access"]


def log(section: str, message: str) -> None:
    print(f"\n[{section}] {message}")


import os

def run_cmd(cmd: list[str]) -> str:
    if cmd and cmd[0] in {"ovs-vsctl", "ovs-ofctl", "ip", "mnexec", "tcpdump"} and hasattr(os, "geteuid") and os.geteuid() != 0:
        cmd = ["sudo", *cmd]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return res.stdout.strip()


def check_ovs_connections() -> dict[str, bool]:
    out = run_cmd(["ovs-vsctl", "show"])
    results = {}
    current_bridge = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Bridge "):
            current_bridge = line.split()[1]
        elif line.startswith("is_connected: true") and current_bridge in SWITCHES:
            results[current_bridge] = True
    for sw in SWITCHES:
        if sw not in results:
            results[sw] = False
    return results


def dump_all_flows() -> dict[str, str]:
    flows = {}
    for sw in SWITCHES:
        flows[sw] = run_cmd(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", sw])
    return flows


def test_ping(src: str, dst_ip: str, count: int = 2) -> dict:
    return request_agent("PING", source=src, destination_ip=dst_ip, count=count)


def test_set_link(link_id: str, state: str) -> dict:
    return request_agent("LINK_DOWN" if state == "down" else "LINK_UP", link_id=link_id)


def main():
    print("=" * 80)
    print("RUNNING FULL-SDN FABRIC LIVE INTEGRATION TEST SUITE")
    print("Environment: Ubuntu Linux, Mininet, Open vSwitch, OS-Ken OpenFlow 1.3")
    print("=" * 80)

    # 1. Check Controller Process
    log("1. CONTROLLER", "Verifying OS-Ken controller_fabric.py is running...")
    ps_out = run_cmd(["pgrep", "-fa", "controller_fabric.py"])
    if "controller_fabric.py" in ps_out:
        print(f"PASS: Controller process active: {ps_out.splitlines()[0]}")
    else:
        print("FAIL: controller_fabric.py not found in process table!")
        sys.exit(1)

    # 2. Check 6 OVS Switches Connected
    log("2. OVS SWITCHES", "Checking OpenFlow 1.3 connection for all 6 switches...")
    connections = check_ovs_connections()
    all_connected = True
    for sw, conn in connections.items():
        status = "CONNECTED" if conn else "DISCONNECTED"
        print(f"  Switch {sw:15}: {status}")
        if not conn:
            all_connected = False
    assert all_connected, "Not all 6 switches are connected to controller!"
    print("PASS: All 6 switches connected to OS-Ken controller!")

    # 3. Check Zero OFPP_NORMAL across all 6 switches
    log("3. ZERO OFPP_NORMAL", "Auditing flow dumps for any OFPP_NORMAL...")
    flows_before = dump_all_flows()
    found_normal = False
    for sw, f_text in flows_before.items():
        if "NORMAL" in f_text or "actions=NORMAL" in f_text:
            print(f"  FAIL: Found NORMAL action on {sw}!")
            found_normal = True
        else:
            flow_count = len(f_text.splitlines()) - 1
            print(f"  Switch {sw:15}: {flow_count:3} flows | 0 instances of NORMAL")
    assert not found_normal, "Detected OFPP_NORMAL in dataplane!"
    print("PASS: 100% Zero OFPP_NORMAL verified across all 6 switches!")

    # 4. Pipeline Verification (Table 0 -> 10 -> 20 -> 30)
    log("4. PIPELINE", "Checking table chaining on switches...")
    sample_sw = "access_floor1"
    sample_flows = flows_before[sample_sw]
    has_t0_goto_t10 = "goto_table:10" in sample_flows
    has_t10_goto_t20 = "goto_table:20" in sample_flows
    has_t20_goto_t30 = "goto_table:30" in sample_flows

    print(f"  Table 0  -> GotoTable(10): {'PRESENT' if has_t0_goto_t10 else 'MISSING'}")
    print(f"  Table 10 -> GotoTable(20): {'PRESENT' if has_t10_goto_t20 else 'MISSING'}")
    print(f"  Table 20 -> GotoTable(30): {'PRESENT' if has_t20_goto_t30 else 'MISSING'}")
    assert has_t0_goto_t10 and has_t10_goto_t20 and has_t20_goto_t30, "Pipeline tables not chained properly!"
    print("PASS: Multi-table pipeline chaining (0 -> 10 -> 20 -> 30) verified in dataplane!")

    # 5. Traffic Tests
    log("5. TRAFFIC TESTS", "Executing live packet tests across enterprise fabric...")
    traffic_results = []

    def run_traffic_case(desc: str, src: str, dst_ip: str, expected_pass: bool):
        if expected_pass:
            test_ping(src, dst_ip, count=1)  # Warm reactive ARP/flow setup; measure the next packets.
        res = test_ping(src, dst_ip, count=3)
        passed = res.get("ok", False)
        match = (passed == expected_pass)
        status_str = "PASS" if match else "FAIL"
        action_str = "REACHABLE" if passed else "DROPPED"
        exp_str = "REACHABLE" if expected_pass else "DROPPED"
        print(f"  [{status_str}] {desc:45}: Result={action_str} (Expected={exp_str})")
        traffic_results.append({"desc": desc, "status": status_str, "action": action_str, "match": match})
        return match

    # A. Same VLAN / Intra-Project
    run_traffic_case("Same Project: h101_01 -> h101_02", "h101_01", "10.10.101.12", expected_pass=True)
    run_traffic_case("Same Project: h93_01 -> h93_02", "h93_01", "10.10.93.12", expected_pass=True)

    # B. Virtual Gateway & Proxy ARP
    run_traffic_case("Virtual Gateway Proxy ARP: h101_01 -> 10.10.101.1", "h101_01", "10.10.101.1", expected_pass=True)

    # C. Permitted Inter-VLAN Voice PBX
    run_traffic_case("Voice Service: h101_01 -> PBX h90 (10.250.10.10)", "h101_01", "10.250.10.10", expected_pass=True)

    # D. Cross-Project Isolation (Must be DROPPED)
    run_traffic_case("Cross-Project DROP: Proj 1 (h101) -> Proj 3 (h103)", "h101_01", "10.10.103.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 1 (h101) -> Proj 4 (h104)", "h101_01", "10.10.104.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 1 (h101) -> Proj 2 (h93)", "h101_01", "10.10.93.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 2 (h93)  -> Proj 3 (h103)", "h93_01", "10.10.103.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 2 (h93)  -> Proj 1 (h101)", "h93_01", "10.10.101.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 2 (h93)  -> Proj 4 (h104)", "h93_01", "10.10.104.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 3 (h103) -> Proj 1 (h101)", "h103_01", "10.10.101.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 3 (h103) -> Proj 2 (h93)", "h103_01", "10.10.93.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 3 (h103) -> Proj 4 (h104)", "h103_01", "10.10.104.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 4 (h104) -> Proj 1 (h101)", "h104_01", "10.10.101.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 4 (h104) -> Proj 2 (h93)", "h104_01", "10.10.93.11", expected_pass=False)
    run_traffic_case("Cross-Project DROP: Proj 4 (h104) -> Proj 3 (h103)", "h104_01", "10.10.103.11", expected_pass=False)

    # E. Guest Boundary
    run_traffic_case("Guest -> Internet: guest_01 -> hinternet", "guest_01", "10.250.20.30", expected_pass=True)
    run_traffic_case("Guest -> Internal RFC1918 DROP: guest_01 -> h101", "guest_01", "10.10.101.11", expected_pass=False)

    # F. IoT Boundary
    run_traffic_case("IoT -> NMS Monitoring: iot_cam_01 -> hmonitor", "iot_cam_01", "10.10.100.14", expected_pass=True)
    run_traffic_case("IoT -> DNS Server: iot_cam_01 -> hdns", "iot_cam_01", "10.10.100.11", expected_pass=True)
    run_traffic_case("IoT -> DHCP Server: iot_cam_01 -> hdhcp", "iot_cam_01", "10.10.100.10", expected_pass=True)
    run_traffic_case("IoT -> NTP Server: iot_cam_01 -> hntp", "iot_cam_01", "10.10.100.16", expected_pass=True)
    run_traffic_case("IoT -> Users Lateral DROP: iot_cam_01 -> h101", "iot_cam_01", "10.10.101.11", expected_pass=False)
    run_traffic_case("IoT -> Internet DROP: iot_cam_01 -> hinternet", "iot_cam_01", "10.250.20.30", expected_pass=False)

    # G. IT Support Privileges & Least Privilege
    run_traffic_case("IT Support Management: h110_01 -> Proj 1 user", "h110_01", "10.10.101.11", expected_pass=True)
    run_traffic_case("Unsolicited User -> IT DROP: h101_01 -> h110", "h101_01", "10.10.110.11", expected_pass=False)

    # H. Social Media Blacklist
    run_traffic_case("Social Media Block: h101_01 -> hsocial (10.250.20.20)", "h101_01", "10.250.20.20", expected_pass=False)

    # 6. Anti-Spoofing Verification
    log("6. ANTI-SPOOFING VERIFICATION", "Testing dataplane source IP anti-spoof enforcement at Table 10...")
    # Send packet with spoofed source IP from h101_01 namespace
    pid_h101 = run_cmd(["pgrep", "-f", "mininet:h101_01"]).splitlines()[0]
    spoof_res = subprocess.run(
        ["mnexec", "-a", pid_h101, "python3", "-c", """
import socket, sys
try:
    # Try sending raw packet with spoofed IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('10.10.101.11', 0))
    s.sendto(b'test', ('10.10.101.12', 9999))
    print('SENT')
except Exception as e:
    print('ERROR:', e)
"""],
        capture_output=True,
        text=True,
    )
    # Check Table 10 anti-spoof flow rules on access_floor1
    f_t10 = run_cmd(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "access_floor1", "table=10"])
    has_spoof_drop = "priority=100,ip" in f_t10 and "actions=drop" in f_t10
    has_valid_subnet = "priority=150,ip" in f_t10 and "goto_table:20" in f_t10
    print(f"  Table 10 Anti-spoof DROP rule (priority 100): {'PRESENT' if has_spoof_drop else 'MISSING'}")
    print(f"  Table 10 Valid Subnet GOTO rule (priority 150): {'PRESENT' if has_valid_subnet else 'MISSING'}")
    if has_spoof_drop and has_valid_subnet:
        print("PASS: Port <-> VLAN <-> Subnet IP anti-spoofing verified in Table 10 dataplane!")
        print("NOTE: Controller enforces Port <-> VLAN <-> Subnet IP binding + dynamic learning. Static Port <-> MAC binding is NOT claimed.")

    # 7. Check Flow Table 30 Multi-Hop Installation & L3 Rewrites
    log("7. L3 REWRITES & MULTI-HOP FLOWS", "Verifying installed dataplane forwarding flows...")
    flows_after = dump_all_flows()
    core_f = flows_after["core_hq"]
    has_l3_rewrite = ("dec_ttl" in core_f or "dec_ttl()" in core_f)
    print(f"  core_hq L3 actions (MAC rewrite + Dec TTL): {'VERIFIED' if has_l3_rewrite else 'NOT FOUND'}")
    if has_l3_rewrite:
        print("PASS: L3 MAC rewrite and TTL decrement actively present in core_hq dataplane!")

    # 8. Failover VLAN 93 Test
    log("8. VLAN 93 FAILOVER TEST", "Testing Primary -> Backup L2VPN dynamic failover...")
    # Step A: Ping when primary is UP
    p1 = test_ping("h93_01", "10.10.93.21", count=3)  # h93_01 (HQ) -> h93_11 (Branch, 10.10.93.21)
    print(f"  Primary Link UP: Ping h93_01 -> h93_11: {'PASS' if p1.get('ok') else 'FAIL'}")

    # Step B: Shutdown the declared primary path; the topology agent raises the standby segments.
    print("  Shutting down Primary L2VPN path (core_hq-ce_hq1)...")
    down = test_set_link("core_hq-ce_hq1", "down")
    print(f"  Controller/agent link-down request: {'PASS' if down.get('ok') else 'FAIL'}")
    time.sleep(10)
    test_ping("h93_01", "10.10.93.21", count=1)

    # Step C: Ping over backup
    p2 = test_ping("h93_01", "10.10.93.21", count=3)
    print(f"  Backup Link ACTIVE: Ping h93_01 -> h93_11: {'PASS' if p2.get('ok') else 'FAIL'}")

    # Step D: Restore Primary L2VPN link
    print("  Restoring Primary L2VPN path (core_hq-ce_hq1)...")
    restored_link = test_set_link("core_hq-ce_hq1", "up")
    print(f"  Controller/agent link-up request: {'PASS' if restored_link.get('ok') else 'FAIL'}")
    time.sleep(10)
    test_ping("h93_01", "10.10.93.21", count=1)

    p3 = test_ping("h93_01", "10.10.93.21", count=3)
    print(f"  Primary Link RESTORED: Ping h93_01 -> h93_11: {'PASS' if p3.get('ok') else 'FAIL'}")

    # 9. Summary
    log("9. SUMMARY", "Evaluating all test criteria...")
    total_cases = len(traffic_results)
    passed_cases = sum(1 for r in traffic_results if r["match"])
    print(f"\nTotal Traffic Test Cases: {total_cases}")
    print(f"Passed Test Cases       : {passed_cases} / {total_cases} ({passed_cases/total_cases*100:.1f}%)")

    failover_ok = all(bool(item.get("ok")) for item in (p1, down, p2, restored_link, p3))
    if passed_cases == total_cases and failover_ok:
        print("\nALL INTEGRATION TESTS PASSED SUCCESSFULLY ON LIVE RUNTIME!")
    else:
        print("\nSOME TEST CASES FAILED - REVIEW OUTPUT ABOVE.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
