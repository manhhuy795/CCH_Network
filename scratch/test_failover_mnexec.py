import subprocess
import sys
import time
sys.path.insert(0, "/home/huy/CCH_Network")

pid = subprocess.run(["pgrep", "-f", "mininet:h93_01"], capture_output=True, text=True).stdout.strip().splitlines()[0]

print("1. Direct Ping before failover:")
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.10.93.21"], capture_output=True, text=True)
print("Before:\n", res.stdout)

# Set DOWN via agent
from sdn_mpls_demo.run_live_tests import test_set_link
print("2. Set DOWN:")
down = test_set_link("core_hq-ce_hq1", "down")
print("Down result:", down.get("status"))

time.sleep(3)

print("3. Direct Ping after failover (run 1):")
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.10.93.21"], capture_output=True, text=True)
print("After failover 1:\n", res.stdout)

print("4. Direct Ping after failover (run 2):")
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "3", "-W", "1", "10.10.93.21"], capture_output=True, text=True)
print("After failover 2:\n", res.stdout)

print("5. Set UP:")
up = test_set_link("core_hq-ce_hq1", "up")
print("Up result:", up.get("status"))

time.sleep(3)

print("6. Direct Ping after restore (run 1):")
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "2", "-W", "1", "10.10.93.21"], capture_output=True, text=True)
print("After restore 1:\n", res.stdout)

print("7. Direct Ping after restore (run 2):")
res = subprocess.run(["mnexec", "-a", pid, "ping", "-c", "3", "-W", "1", "10.10.93.21"], capture_output=True, text=True)
print("After restore 2:\n", res.stdout)
