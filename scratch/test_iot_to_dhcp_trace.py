import subprocess
import time

pid_iot = subprocess.run(["pgrep", "-f", "mininet:iot_cam_01"], capture_output=True, text=True).stdout.strip()
pid_dhcp = subprocess.run(["pgrep", "-f", "mininet:hdhcp"], capture_output=True, text=True).stdout.strip()
print("iot_cam_01 PID:", pid_iot)
print("hdhcp PID:", pid_dhcp)

# Start tcpdump on hdhcp interface
p_dhcp = subprocess.Popen(["mnexec", "-a", pid_dhcp, "tcpdump", "-l", "-n", "-e", "-i", "h100s01-eth0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
# Start tcpdump on iot_cam_01 interface
p_iot = subprocess.Popen(["mnexec", "-a", pid_iot, "tcpdump", "-l", "-n", "-e", "-i", "h140u01-eth0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

# Send ping from iot_cam_01 to hdhcp (10.10.100.10)
res = subprocess.run(["mnexec", "-a", pid_iot, "ping", "-c", "3", "-W", "1", "10.10.100.10"], capture_output=True, text=True)
print("PING RESULT:\n", res.stdout)

time.sleep(1)
p_dhcp.terminate()
p_iot.terminate()
out_dhcp, _ = p_dhcp.communicate()
out_iot, _ = p_iot.communicate()

print("TCPDUMP ON HDHCP:\n", out_dhcp)
print("TCPDUMP ON IOT:\n", out_iot)
