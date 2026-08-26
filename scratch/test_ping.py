import subprocess

pid = subprocess.check_output(["pgrep", "-f", "mininet:h101_01"]).decode().strip().splitlines()[0]
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "3", "10.10.101.12"], capture_output=True, text=True)
print("Return code:", res.returncode)
print(res.stdout)
