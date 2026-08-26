import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:hq_l3_gateway"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "ip", "neigh"], capture_output=True, text=True)
print("hq_l3_gateway ARP table:\n", res.stdout)
