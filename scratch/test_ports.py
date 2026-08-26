import json

state = json.load(open("/home/huy/CCH_Network/sdn_mpls_demo/runtime/fabric_state.json"))
print("hmonitor in hosts_by_ip:")
for h, info in state.get("hosts_by_ip", {}).items():
    if "monitor" in info.get("name", "") or "10.10.100.14" in h:
        print(" ", h, info)
print("hdns in hosts_by_ip:")
for h, info in state.get("hosts_by_ip", {}).items():
    if "dns" in info.get("name", "") or "10.10.100.11" in h:
        print(" ", h, info)
