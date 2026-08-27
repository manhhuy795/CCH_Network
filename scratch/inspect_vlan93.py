import subprocess

pid = subprocess.run(["pgrep", "-f", "mininet:h93_01"], capture_output=True, text=True).stdout.strip().splitlines()[0]

res = subprocess.run(["mnexec", "-a", pid, "ip", "neigh"], capture_output=True, text=True)
print("NEIGH on h93_01:\n", res.stdout)

pid2 = subprocess.run(["pgrep", "-f", "mininet:h93_11"], capture_output=True, text=True).stdout.strip().splitlines()[0]
res2 = subprocess.run(["mnexec", "-a", pid2, "ip", "neigh"], capture_output=True, text=True)
print("NEIGH on h93_11:\n", res2.stdout)

res3 = subprocess.run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "core_hq", "table=30"], capture_output=True, text=True)
print("core_hq table 30:\n", res3.stdout)

res4 = subprocess.run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "dist_branch", "table=30"], capture_output=True, text=True)
print("dist_branch table 30:\n", res4.stdout)
