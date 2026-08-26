import sys
sys.path.insert(0, "/home/huy/CCH_Network/sdn_mpls_demo/.venv/lib/python3.10/site-packages")
from os_ken.ofproto import ofproto_v1_3_parser
parser = ofproto_v1_3_parser
try:
    m = parser.OFPMatch(eth_type=0x0800, ip_proto=1, icmpv4_type=0)
    print("MATCH OK:", m)
except Exception as e:
    print("MATCH ERROR:", e)
