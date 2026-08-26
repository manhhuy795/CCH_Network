import subprocess
import time

p = subprocess.Popen(["tcpdump", "-i", "core-eth03", "-n", "-e", "-c", "5"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)
pid = subprocess.check_output(["pgrep", "-f", "mininet:h101_01"]).decode().strip().splitlines()[0]
subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.250.10.10"], capture_output=True)
stdout, stderr = p.communicate(timeout=5)
print("TCPDUMP OUTPUT ON core-eth03:\n", stdout)
print("STDERR:\n", stderr)
