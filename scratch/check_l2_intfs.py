import subprocess

for node in ["core_hq", "ce_hq2", "l2vpn_backup", "ce_branch2", "dist_branch"]:
    res = subprocess.run(["ip", "link", "show"], capture_output=True, text=True)
    matching = [l.strip() for l in res.stdout.splitlines() if "eth93" in l or "cehq2" in l or "l2b" in l or "cebr2" in l]
    print(f"Interfaces: {matching}")
    break
