import subprocess

for sw in ["access_floor1", "core_hq", "dist_branch", "access_branch"]:
    res = subprocess.run(["sudo", "ovs-ofctl", "-O", "OpenFlow13", "dump-flows", sw], capture_output=True, text=True)
    print(f"=== {sw} ===")
    for line in res.stdout.splitlines():
        if "10.10.93.21" in line or ("nw_dst=10.10.93." in line and "actions=" in line):
            print(" ", line.strip())
