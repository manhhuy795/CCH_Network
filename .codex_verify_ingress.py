import json
import sys
from pathlib import Path

repo = Path("/home/huy/CCH_Network")
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / "dashboard" / "backend"))

from sdn_mpls_demo.run_live_tests import check_ovs_connections, dump_all_flows, verify_ingress_port_coverage

connections = check_ovs_connections()
assert all(connections.values()), connections
flows = dump_all_flows()
assert all("NORMAL" not in flow for flow in flows.values())
verify_ingress_port_coverage()

state = json.loads((repo / "sdn_mpls_demo/runtime/fabric_state.json").read_text())
incomplete = [item["name"] for item in state["switches"].values() if not item.get("port_inventory_complete")]
assert not incomplete, incomplete
print("CONNECTED", connections)
print("INVENTORY_COMPLETE", len(state["switches"]), "/", len(state["switches"]))
print("NO_OFPP_NORMAL", len(flows), "/", len(flows))
