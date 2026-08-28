import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.controller_fabric import FullSDNFabricController, PolicyEngine, POLICY_FILE

print("Loading PolicyEngine with:", POLICY_FILE)
pe = PolicyEngine(POLICY_FILE)
print("Keys in policies:", list(pe.data.get("policies", {}).keys()))
it_pol = pe.data["policies"].get("it_support_controlled_access")
print("it_support_controlled_access:", it_pol)
