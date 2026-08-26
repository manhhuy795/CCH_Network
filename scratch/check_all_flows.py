import subprocess

for sw in ["core_hq", "dist_branch", "access_floor1", "access_floor2", "access_branch", "infra_access"]:
    res = subprocess.run(["sudo", "ovs-ofctl", "-O", "OpenFlow13", "dump-flows", sw], capture_output=True, text=True)
    flows = [line for line in res.stdout.splitlines() if "cookie" in line]
    print(f"Switch {sw:15}: {len(flows)} flows")
