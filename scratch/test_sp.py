import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.controller_fabric import FabricTopology
import json

topo = FabricTopology()
state = json.load(open("/home/huy/CCH_Network/sdn_mpls_demo/runtime/fabric_state.json"))
for c in state.get("topology_circuits", []):
    topo.add_link(c["source"], c["target"], c["local_port"], c["local_port"], circuit_id=c["circuit_id"], role=c["role"], status=c["status"], vlans=set(c["vlans"]))

print("Shortest path for VLAN 93 access_floor1 -> access_branch:")
p = topo.shortest_path("access_floor1", "access_branch", vlan=93)
print("Path:", p)
for i in range(len(p)-1):
    u, v = p[i], p[i+1]
    egress = topo.egress_port_for_next_hop(u, v, vlan=93)
    print(f"  {u} -> {v} egress_port={egress}")
