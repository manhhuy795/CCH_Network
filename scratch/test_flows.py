import subprocess

res = subprocess.run(["sudo", "ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "core_hq"], capture_output=True, text=True)
print("=== core_hq flows ===")
for line in res.stdout.splitlines():
    if "10.250.10.10" in line or "10.250.20.30" in line or "table=30" in line and "output:" in line:
        print(" ", line.strip())
