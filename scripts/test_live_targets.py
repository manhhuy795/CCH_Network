import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.run_live_tests import test_ping

print("IoT -> DHCP Server (10.10.100.10):", test_ping("iot_cam_01", "10.10.100.10", count=3))
print("Guest -> Internet (10.250.20.30):", test_ping("guest_01", "10.250.20.30", count=3))
print("h93_01 -> h93_11 (VLAN 93 L2VPN):", test_ping("h93_01", "10.10.93.21", count=3))
