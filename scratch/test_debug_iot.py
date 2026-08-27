import subprocess

pid = subprocess.run(["pgrep", "-f", "mininet:iot_cam_01"], capture_output=True, text=True).stdout.strip()
print("iot_cam_01 PID:", pid)

# Check route
res = subprocess.run(["mnexec", "-a", pid, "ip", "route"], capture_output=True, text=True)
print("ROUTES:\n", res.stdout)

# Check ARP
res = subprocess.run(["mnexec", "-a", pid, "ip", "neigh"], capture_output=True, text=True)
print("NEIGH:\n", res.stdout)

# Ping with verbose / debug
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-v", "10.10.100.10"], capture_output=True, text=True)
print("PING 10.10.100.10:\n", res.stdout, res.stderr)
