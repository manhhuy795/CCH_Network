import subprocess

for node in ["h101_01", "h101_02", "h93_01", "h93_11", "guest_01", "iot_cam_01"]:
    pid = subprocess.check_output(["pgrep", "-f", f"mininet:{node}"]).decode().strip().splitlines()[0]
    out = subprocess.check_output(["mnexec", "-a", pid, "ip", "addr", "show"]).decode()
    route = subprocess.check_output(["mnexec", "-a", pid, "ip", "route", "show"]).decode()
    print(f"=== Node {node} (pid {pid}) ===")
    for line in out.splitlines():
        if "inet " in line:
            print("  ", line.strip())
    for line in route.splitlines():
        print("  route:", line.strip())
