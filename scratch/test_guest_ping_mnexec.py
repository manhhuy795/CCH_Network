import subprocess

pid = subprocess.run(["pgrep", "-f", "mininet:guest_01"], capture_output=True, text=True).stdout.strip().splitlines()[0]
print("guest_01 PID:", pid)

for i in range(3):
    res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "3", "10.250.20.30"], capture_output=True, text=True)
    print(f"Run {i+1}:", "0% packet loss" in res.stdout, res.stdout.splitlines()[-2:])
