import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.controller_fabric import FullSDNFabricController, DPID_NAMES, ALL_GATEWAY_IPS

app = FullSDNFabricController()
print("10.10.120.1 in ALL_GATEWAY_IPS?", "10.10.120.1" in ALL_GATEWAY_IPS)
print("10.10.101.1 in ALL_GATEWAY_IPS?", "10.10.101.1" in ALL_GATEWAY_IPS)
print("ALL_GATEWAY_IPS:", sorted(ALL_GATEWAY_IPS))
