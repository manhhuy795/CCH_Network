import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:fw_hq"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "nft", "list", "ruleset"], capture_output=True, text=True)
print("fw_hq nftables ruleset:\n", res.stdout)
