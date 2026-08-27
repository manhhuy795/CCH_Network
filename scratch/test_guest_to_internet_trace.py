import subprocess
import time

pid_guest = subprocess.run(["pgrep", "-f", "mininet:guest_01"], capture_output=True, text=True).stdout.strip()
print("guest_01 PID:", pid_guest)

# Start tcpdump on guest_01 interface
p_guest = subprocess.Popen(["mnexec", "-a", pid_guest, "tcpdump", "-l", "-n", "-e", "-i", "h120u01-eth0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

# Send ping from guest_01 to hinternet (10.250.20.30)
res = subprocess.run(["mnexec", "-a", pid_guest, "ping", "-c", "3", "-W", "1", "10.250.20.30"], capture_output=True, text=True)
print("PING RESULT:\n", res.stdout)

time.sleep(1)
p_guest.terminate()
out_guest, _ = p_guest.communicate()

print("TCPDUMP ON GUEST:\n", out_guest)
