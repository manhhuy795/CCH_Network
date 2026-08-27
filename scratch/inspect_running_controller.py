import socket
import json

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/tmp/cch_osken_admin.sock")
s.sendall(json.dumps({"token": "cch-local-admin-token", "action": "get_state"}).encode("utf-8") + b"\n")
data = s.recv(65536).decode("utf-8")
print("Response:", data[:1000])
