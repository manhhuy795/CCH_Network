import subprocess
import time

pid_gw = subprocess.check_output(["pgrep", "-f", "mininet:hq_l3_gateway"]).decode().strip().splitlines()[0]
p = subprocess.Popen(["mnexec", "-a", pid_gw, "tcpdump", "-i", "v101-eth0", "-n", "-e", "-c", "3"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

pid_h101 = subprocess.check_output(["pgrep", "-f", "mininet:h101_01"]).decode().strip().splitlines()[0]
subprocess.run(["mnexec", "-a", pid_h101, "ping", "-c", "2", "-W", "1", "10.250.10.10"], capture_output=True)

try:
    stdout, stderr = p.communicate(timeout=4)
    print("TCPDUMP on hq_l3_gateway v101-eth0:\n", stdout)
except subprocess.TimeoutExpired:
    p.kill()
    print("TIMEOUT: No packets arrived on v101-eth0!")
