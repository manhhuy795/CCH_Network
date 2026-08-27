import subprocess
import time

print("=== STARTING DHCP BOOTSTRAP END-TO-END DORA TEST ===")

# 1. Clear dnsmasq log
subprocess.run(["sudo", "truncate", "-s", "0", "/tmp/dnsmasq.log"])

# 2. Start tcpdump on hdhcp-eth0 (Server) and capture
p_server = subprocess.Popen(
    ["sudo", "tcpdump", "-i", "inf-s01", "-n", "-vv", "udp", "port", "67", "or", "port", "68", "-c", "4"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

time.sleep(1)

# 3. Find guest_01 PID and run dhclient
pid = subprocess.run(["pgrep", "-f", "mininet:guest_01"], capture_output=True, text=True).stdout.strip().splitlines()[0]
print("Target host: guest_01 (PID:", pid, ")")

# Release existing lease if any and request fresh IP
subprocess.run(["sudo", "mnexec", "-a", pid, "dhclient", "-r", "h120u01-eth0"], capture_output=True, text=True)
time.sleep(1)

print("Executing dhclient on guest_01...")
dhclient_res = subprocess.run(
    ["sudo", "mnexec", "-a", pid, "timeout", "6", "dhclient", "-v", "-1", "h120u01-eth0"],
    capture_output=True,
    text=True
)
print("DHCLIENT STDOUT:\n", dhclient_res.stdout)
print("DHCLIENT STDERR:\n", dhclient_res.stderr)

time.sleep(1)
p_server.terminate()
server_out, _ = p_server.communicate()
print("\nTCPDUMP ON DHCP SERVER (inf-s01):\n", server_out)

dnsmasq_log = subprocess.run(["sudo", "cat", "/tmp/dnsmasq.log"], capture_output=True, text=True).stdout
print("\nDNSMASQ LOG (/tmp/dnsmasq.log):\n", dnsmasq_log)

# Check for DORA presence
dora_steps = ["DHCPDISCOVER", "DHCPOFFER", "DHCPREQUEST", "DHCPACK"]
all_dora = all(step in dnsmasq_log or step in dhclient_res.stderr for step in dora_steps)
print("\nDORA SEQUENCE COMPLETE:", all_dora)
if all_dora:
    print("PASS: DHCP DISCOVER -> OFFER -> REQUEST -> ACK verified end-to-end through full-SDN fabric!")
else:
    print("WARNING: Some DORA steps missing from output. Review logs above.")
