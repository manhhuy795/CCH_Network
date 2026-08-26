import subprocess

res = subprocess.run(["sudo", "ovs-vsctl", "show"], capture_output=True, text=True)
out = res.stdout.strip()
print("Length of ovs-vsctl show:", len(out))

SWITCHES = ["core_hq", "dist_branch", "access_floor1", "access_floor2", "access_branch", "infra_access"]
results = {}
current_bridge = None
for line in out.splitlines():
    line = line.strip()
    if line.startswith("Bridge "):
        current_bridge = line.split()[1]
        print("Found bridge:", current_bridge)
    elif line.startswith("is_connected: true") and current_bridge in SWITCHES:
        print("Bridge", current_bridge, "is_connected!")
        results[current_bridge] = True
print("Results:", results)
