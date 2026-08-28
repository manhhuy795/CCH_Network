import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.run_live_tests import check_ovs_connections
print("Connection Status:", check_ovs_connections())
