import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.run_live_tests import test_ping

test_ping("guest_01", "10.250.20.30", count=2)
print("guest_01 -> 10.250.20.30:", test_ping("guest_01", "10.250.20.30", count=3))
