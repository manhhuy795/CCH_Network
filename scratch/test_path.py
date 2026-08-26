import json
state = json.load(open("/home/huy/CCH_Network/sdn_mpls_demo/runtime/fabric_state.json"))
circuits = state.get("topology_circuits", [])
print("Topology circuits count:", len(circuits))
for c in circuits:
    print(f"  {c['source']:15} -> {c['target']:15} local_port={c['local_port']} role={c['role']:8} status={c['status']:7} circuit={c['circuit_id']}")
