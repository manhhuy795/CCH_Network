import subprocess

res = subprocess.run(["sudo", "ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "access_floor1", "table=30"], capture_output=True, text=True)
print("=== access_floor1 table 30 flows ===")
print(res.stdout)
