import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:iot_cam_01"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.10.100.14"], capture_output=True, text=True)
print("Ping iot_cam_01 -> 10.10.100.14:\n", res.stdout)

f_inf = subprocess.run(["sudo", "ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "infra_access"], capture_output=True, text=True)
print("=== infra_access flows ===")
for line in f_inf.stdout.splitlines():
    if "10.10.100.14" in line or "10.10.140.101" in line:
        print(" ", line.strip())

f_core = subprocess.run(["sudo", "ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "core_hq"], capture_output=True, text=True)
print("=== core_hq flows ===")
for line in f_core.stdout.splitlines():
    if "10.10.100.14" in line or "10.10.140.101" in line:
        print(" ", line.strip())
