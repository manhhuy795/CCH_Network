import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from sdn_mpls_demo.run_live_tests import test_ping
import json

for src, dst in [
    ("h101_01", "10.10.101.12"),
    ("h101_01", "10.10.101.1"),
    ("h93_01", "10.10.93.12"),
    ("guest_01", "10.250.20.30"),
]:
    res = test_ping(src, dst, count=2)
    print(f"PING {src} -> {dst}: ok={res.get('ok')} raw={res.get('raw')}")
