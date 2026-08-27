import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.run_live_tests import test_ping

print("1. Ping iot_cam_01 -> 10.10.100.10:")
r1 = test_ping("iot_cam_01", "10.10.100.10", count=3)
print("r1:", r1)

print("2. Ping guest_01 -> 10.250.20.30:")
r2 = test_ping("guest_01", "10.250.20.30", count=3)
print("r2:", r2)

print("3. Ping h93_01 -> 10.10.93.21:")
r3 = test_ping("h93_01", "10.10.93.21", count=3)
print("r3:", r3)
