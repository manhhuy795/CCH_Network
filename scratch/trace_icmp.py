import subprocess
import time

# Start tcpdump on core-eth01 (from access_floor1), core-eth03 (to fw_hq)
p1 = subprocess.Popen(["tcpdump", "-i", "core-eth01", "-n", "icmp", "-c", "4"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
p2 = subprocess.Popen(["tcpdump", "-i", "core-eth03", "-n", "icmp", "-c", "4"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

time.sleep(1)

# Ping from guest_01
pid = subprocess.run(["pgrep", "-f", "mininet:guest_01"], capture_output=True, text=True).stdout.strip().splitlines()[0]
subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.250.20.30"], capture_output=True, text=True)

time.sleep(1)
p1.terminate()
p2.terminate()
out1, _ = p1.communicate()
out2, _ = p2.communicate()

print("core-eth01 ICMP:\n", out1)
print("core-eth03 ICMP:\n", out2)
