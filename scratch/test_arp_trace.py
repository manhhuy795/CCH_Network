import subprocess
import time

pid = subprocess.run(["pgrep", "-f", "mininet:guest_01"], capture_output=True, text=True).stdout.strip()
print("guest_01 PID:", pid)

# Start tcpdump on guest_01 interface
p = subprocess.Popen(["mnexec", "-a", pid, "tcpdump", "-l", "-nn", "-e", "-i", "h120u01-eth0", "arp"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

# Send ping from guest_01 to gateway 10.10.120.1
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.10.120.1"], capture_output=True, text=True)
print("ARPING STDOUT:\n", res.stdout)
print("ARPING STDERR:\n", res.stderr)

time.sleep(1)
p.terminate()
out, err = p.communicate()
print("TCPDUMP ON GUEST_01:\n", out)
