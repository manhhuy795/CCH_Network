import subprocess
import time

# Start tcpdump on hinternet
p = subprocess.Popen(["tcpdump", "-l", "-nn", "-i", "hinternet-eth0", "icmp"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

# Ping from guest_01
pid = subprocess.run(["pgrep", "-f", "mininet:guest_01"], capture_output=True, text=True).stdout.strip()
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.250.20.30"], capture_output=True, text=True)
print("PING STDOUT:", res.stdout)
print("PING STDERR:", res.stderr)

time.sleep(1)
p.terminate()
out, err = p.communicate()
print("TCPDUMP ON HINTERNET:")
print(out)
