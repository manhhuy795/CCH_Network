import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:iot_cam_01"]).decode().strip().splitlines()[0]
for target, desc in [("10.10.100.10", "hdhcp"), ("10.10.100.11", "hdns"), ("10.10.100.14", "hmonitor")]:
    res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", target], capture_output=True, text=True)
    print(f"iot_cam_01 -> {desc} ({target}): {'PASS' if ' 0% packet loss' in res.stdout else 'FAIL'}")
