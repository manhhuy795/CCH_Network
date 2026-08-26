import subprocess
import time

pid_h101 = subprocess.check_output(["pgrep", "-f", "mininet:h101_01"]).decode().strip().splitlines()[0]
pid_gw = subprocess.check_output(["pgrep", "-f", "mininet:hq_l3_gateway"]).decode().strip().splitlines()[0]

p = subprocess.Popen(["mnexec", "-a", pid_gw, "tcpdump", "-i", "any", "-n", "-c", "10"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

res = subprocess.run(["mnexec", "-a", pid_h101, "ping", "-c", "2", "-W", "1", "10.250.10.10"], capture_output=True, text=True)
print("Ping stdout:\n", res.stdout)
print("Ping stderr:\n", res.stderr)

try:
    stdout, stderr = p.communicate(timeout=3)
    print("TCPDUMP on hq_l3_gateway:\n", stdout)
except subprocess.TimeoutExpired:
    p.kill()
    print("TIMEOUT: No packets arrived on hq_l3_gateway!")
