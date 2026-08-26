import subprocess

subprocess.run(["mn", "-c"], capture_output=True)

# Get all links
res = subprocess.run(["ip", "-o", "link", "show"], capture_output=True, text=True)
for line in res.stdout.splitlines():
    parts = line.split(":")
    if len(parts) >= 2:
        name = parts[1].strip().split("@")[0]
        if name not in {"lo", "ens33", "ens32", "ens160", "eth0"} and not name.startswith("ens"):
            subprocess.run(["ip", "link", "del", name], capture_output=True)

# Delete OVS bridges
bridges = [
    "access_floor1", "access_floor2", "core_hq", "access_branch", "dist_branch", "infra_access",
    "service_net", "ce_hq1", "ce_hq2", "ce_branch1", "ce_branch2", "l2vpn_primary", "l2vpn_backup"
]
for br in bridges:
    subprocess.run(["ovs-vsctl", "--if-exists", "del-br", br], capture_output=True)

subprocess.run(["pkill", "-9", "-f", "topology"], capture_output=True)
subprocess.run(["rm", "-f", "/tmp/cch-sdn-topology.lock"], capture_output=True)
print("CLEANUP_COMPLETE")
