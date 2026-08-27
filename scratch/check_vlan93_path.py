import sys
sys.path.insert(0, ".")
from sdn_mpls_demo.controller_fabric import FullSDNFabricController

app = FullSDNFabricController()
print("Links in topology:")
for (u, v), circuits in app.topo.links.items():
    for c in circuits:
        print(f"  {u} -> {v}: vlans={c['vlans']} status={c['status']} role={c['role']}")
