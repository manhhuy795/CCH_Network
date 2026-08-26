import subprocess
import json
from pathlib import Path

p = subprocess.run(["ps", "aux"], capture_output=True, text=True)
hosts = {}
for line in p.stdout.splitlines():
    if "mininet:" in line:
        parts = line.split()
        pid = parts[1]
        h_name = line.split("mininet:")[-1].strip().split()[0]
        hosts[h_name] = pid
print(f"Found {len(hosts)} mininet host processes.")

host_macs = {}
for h, pid in hosts.items():
    try:
        devs_out = subprocess.run(["mnexec", "-a", pid, "ls", "/sys/class/net"], capture_output=True, text=True)
        devs = [d for d in devs_out.stdout.split() if d != "lo"]
        if devs:
            mac_out = subprocess.run(["mnexec", "-a", pid, "cat", f"/sys/class/net/{devs[0]}/address"], capture_output=True, text=True)
            mac = mac_out.stdout.strip()
            if mac:
                host_macs[h] = mac
    except Exception:
        pass


out_path = Path("/home/huy/CCH_Network/sdn_mpls_demo/runtime/host_macs.json")
out_path.write_text(json.dumps(host_macs, indent=2))
print(f"Dumped {len(host_macs)} host MACs to {out_path}!")
for h in ["h101_01", "h101_02", "h93_01", "h93_11", "hdns", "hmonitor", "guest_01", "iot_cam_01"]:
    print(f"  {h:15}: {host_macs.get(h)}")
