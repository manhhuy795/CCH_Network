import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:fw_hq"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.250.10.10"], capture_output=True, text=True)
print("Ping from fw_hq to 10.250.10.10:\n", res.stdout)
print("Stderr:\n", res.stderr)

pid_inet = subprocess.check_output(["pgrep", "-f", "mininet:internet_zone"]).decode().strip().splitlines()[0]
res_inet = subprocess.run(["mnexec", "-a", pid_inet, "ping", "-c", "2", "-W", "1", "10.250.10.10"], capture_output=True, text=True)
print("Ping from internet_zone to 10.250.10.10:\n", res_inet.stdout)
