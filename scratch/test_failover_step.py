import sys
import time
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.run_live_tests import test_ping, test_set_link

print("1. Ping before failover:")
r1 = test_ping("h93_01", "10.10.93.21", count=2)
print("r1:", r1)

print("2. Set core_hq-ce_hq1 DOWN:")
down = test_set_link("core_hq-ce_hq1", "down")
print("down:", down)

time.sleep(3)

print("3. Ping after failover (warmup):")
r_warm = test_ping("h93_01", "10.10.93.21", count=2)
print("r_warm:", r_warm)

print("4. Ping after failover (test):")
r2 = test_ping("h93_01", "10.10.93.21", count=3)
print("r2:", r2)

print("5. Restore core_hq-ce_hq1 UP:")
up = test_set_link("core_hq-ce_hq1", "up")
print("up:", up)

time.sleep(3)

print("6. Ping after restore (warmup):")
r_rest = test_ping("h93_01", "10.10.93.21", count=2)
print("r_rest:", r_rest)

print("7. Ping after restore (test):")
r3 = test_ping("h93_01", "10.10.93.21", count=3)
print("r3:", r3)
