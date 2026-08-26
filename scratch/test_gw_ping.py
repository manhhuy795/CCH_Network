import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:hq_l3_gateway"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "ip", "route", "show"], capture_output=True, text=True)
print("hq_l3_gateway routes:\n", res.stdout)

pid_fw = subprocess.check_output(["pgrep", "-f", "mininet:fw_hq"]).decode().strip().splitlines()[0]
res_fw = subprocess.run(["mnexec", "-a", pid_fw, "ip", "route", "show"], capture_output=True, text=True)
print("fw_hq routes:\n", res_fw.stdout)
