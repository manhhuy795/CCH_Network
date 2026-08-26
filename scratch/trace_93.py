import subprocess
import time

pid_1 = subprocess.check_output(["pgrep", "-f", "mininet:h93_01"]).decode().strip().splitlines()[0]
pid_11 = subprocess.check_output(["pgrep", "-f", "mininet:h93_11"]).decode().strip().splitlines()[0]

p = subprocess.Popen(["mnexec", "-a", pid_11, "tcpdump", "-i", "h93u11-eth0", "-n", "-e", "-c", "5"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

res = subprocess.run(["mnexec", "-a", pid_1, "ping", "-c", "3", "-W", "1", "10.10.93.21"], capture_output=True, text=True)
print("Ping h93_01 -> h93_11:\n", res.stdout)
print("Stderr:\n", res.stderr)

try:
    stdout, stderr = p.communicate(timeout=3)
    print("TCPDUMP on h93_11:\n", stdout)
except subprocess.TimeoutExpired:
    p.kill()
    print("TIMEOUT: No packets arrived on h93_11!")
