import subprocess
import time

p = subprocess.Popen(["tcpdump", "-i", "bd-eth93p", "-n", "icmp", "-c", "3"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

pid = subprocess.run(["pgrep", "-f", "mininet:h93_01"], capture_output=True, text=True).stdout.strip().splitlines()[0]
subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.10.93.21"], capture_output=True, text=True)

time.sleep(1)
p.terminate()
out, _ = p.communicate()
print("bd-eth93p ICMP:\n", out)
