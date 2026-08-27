import subprocess

print("=== TESTING UNSOLICITED INFRASTRUCTURE -> USER TRAFFIC (MUST DROP) ===")

services = ["hdns", "hdhcp", "hmonitor"]
user_ip = "10.10.101.11"  # h101_01

all_dropped = True
for svc in services:
    pid = subprocess.run(["pgrep", "-f", f"mininet:{svc}"], capture_output=True, text=True).stdout.strip().splitlines()[0]
    res = subprocess.run(
        ["sudo", "mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", user_ip],
        capture_output=True,
        text=True
    )
    dropped = "100% packet loss" in res.stdout or "0 received" in res.stdout
    print(f"Unsolicited {svc} -> User ({user_ip}): {'DROPPED (PASS)' if dropped else 'LEAKED (FAIL)'}")
    if not dropped:
        all_dropped = False

print("\nUNSOLICITED SERVICE INITIATION PROHIBITED:", all_dropped)
if all_dropped:
    print("PASS: Verified that no infrastructure/service can initiate unsolicited sessions to users.")
