import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:h101_01"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "3", "-W", "1", "10.250.10.10"], capture_output=True, text=True)
print("Ping h101_01 -> 10.250.10.10:\n", res.stdout)
print("Stderr:\n", res.stderr)

pid_g = subprocess.check_output(["pgrep", "-f", "mininet:guest_01"]).decode().strip().splitlines()[0]
res_g = subprocess.run(["mnexec", "-a", pid_g, "ping", "-c", "3", "-W", "1", "10.250.20.30"], capture_output=True, text=True)
print("Ping guest_01 -> 10.250.20.30:\n", res_g.stdout)
