import subprocess
import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.run_live_tests import test_ping

pid = subprocess.run(["pgrep", "-f", "mininet:guest_01"], capture_output=True, text=True).stdout.strip()
print("1. Direct mnexec ping:")
res1 = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.250.20.30"], capture_output=True, text=True)
print("res1:\n", res1.stdout)

print("2. Agent request_agent ping:")
res2 = test_ping("guest_01", "10.250.20.30", count=2)
print("res2:\n", res2)
