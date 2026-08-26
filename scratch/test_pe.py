from pathlib import Path
import sys

sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.policy_engine import PolicyEngine

pe = PolicyEngine(Path("/home/huy/CCH_Network/sdn_mpls_demo/policy.yml"))
for pair in [
    ("10.10.101.11", "10.10.101.12"),
    ("10.10.101.11", "10.10.101.1"),
    ("10.10.101.11", "10.250.10.10"),
    ("10.10.120.101", "10.250.30.30"),
    ("10.10.140.101", "10.10.100.11"),
]:
    dec = pe.decide_ip(pair[0], pair[1])
    print(f"{pair[0]} -> {pair[1]}: action={dec['action']}, reason={dec.get('reason')}")
