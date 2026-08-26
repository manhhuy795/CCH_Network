import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:hmonitor"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "ip", "addr"], capture_output=True, text=True)
print("hmonitor ip addr:\n", res.stdout)
res2 = subprocess.run(["mnexec", "-a", pid, "ip", "route"], capture_output=True, text=True)
print("hmonitor ip route:\n", res2.stdout)
