import subprocess
import time

pid = subprocess.run(["pgrep", "-f", "mininet:iot_cam_01"], capture_output=True, text=True).stdout.strip()
print("iot_cam_01 PID:", pid)

# Start tcpdump on iot_cam_01
p = subprocess.Popen(["mnexec", "-a", pid, "tcpdump", "-l", "-n", "-e", "-i", "h140u01-eth0"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(1)

# Send arping / ping to gateway 10.10.140.1
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.10.140.1"], capture_output=True, text=True)
print("PING STDOUT:\n", res.stdout)

time.sleep(1)
p.terminate()
out, err = p.communicate()
print("TCPDUMP ON IOT_CAM_01:\n", out)
