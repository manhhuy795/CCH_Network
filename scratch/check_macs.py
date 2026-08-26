import subprocess

for h in ["h101_01", "h101_02", "hdns", "hmonitor", "h110_01", "guest_01", "iot_cam_01"]:
    try:
        pid = subprocess.check_output(["pgrep", "-f", f"mininet:{h}"]).decode().strip().splitlines()[0]
        devs = [d for d in subprocess.check_output(["mnexec", "-a", pid, "ls", "/sys/class/net"]).decode().split() if d != "lo"]
        if devs:
            mac = subprocess.check_output(["mnexec", "-a", pid, "cat", f"/sys/class/net/{devs[0]}/address"]).decode().strip()
            print(f"{h} ({devs[0]}): {mac}")
    except Exception as e:
        print(f"Error {h}: {e}")
