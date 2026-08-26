import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from pathlib import Path
from sdn_mpls_demo.policy_engine import PolicyEngine

pe = PolicyEngine(Path("/home/huy/CCH_Network/sdn_mpls_demo/policy.yml"))
print("guest -> internet:", pe.decide_ip("10.10.120.101", "10.250.20.30"))
print("internet -> guest:", pe.decide_ip("10.250.20.30", "10.10.120.101"))
