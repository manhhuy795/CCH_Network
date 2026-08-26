import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:hq_l3_gateway"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "ip", "addr", "show"], capture_output=True, text=True)
print("hq_l3_gateway IP and interfaces:\n", res.stdout)
