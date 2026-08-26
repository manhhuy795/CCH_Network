import socket
import json

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/tmp/cch_osken_admin.sock")
s.sendall(json.dumps({"token": "cch-local-admin-token", "command": "GET_STATE"}).encode("utf-8") + b"\n")
data = s.recv(16384).decode("utf-8")
state = json.loads(data)
print("State keys:", list(state.keys()))
print("Full state:", json.dumps(state, indent=2)[:1000])
