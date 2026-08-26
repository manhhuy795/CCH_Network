import sys
import json
import socket

sys.path.insert(0, "/home/huy/CCH_Network/dashboard/backend")
from app.mininet_control import request_agent

res = request_agent("PING", source="h101_01", destination_ip="10.10.101.12", count=2)
print("PING RESULT:", json.dumps(res, indent=2))
