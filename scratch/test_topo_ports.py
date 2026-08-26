import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.controller_fabric import FullSDNFabricController

c = FullSDNFabricController()
p1 = c.topo.egress_port_for_next_hop("core_hq", "access_floor1", vlan=120)
p2 = c.topo.egress_port_for_next_hop("access_floor1", "core_hq", vlan=120)
print("core_hq -> access_floor1 (vlan 120):", p1)
print("access_floor1 -> core_hq (vlan 120):", p2)
print("port_name_to_no core_hq:", c.topo.port_name_to_no.get("core_hq"))
