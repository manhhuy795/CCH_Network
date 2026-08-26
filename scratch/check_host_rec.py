import sys
sys.path.insert(0, "/home/huy/CCH_Network")
from scripts.network_model import load_network_model, build_host_inventory

model = load_network_model()
inv = build_host_inventory(model)
for ip in ["10.10.101.11", "10.10.101.12", "10.10.100.10", "10.10.100.11", "10.10.100.14", "10.250.10.10", "10.250.20.30"]:
    found = [h for h in inv.values() if h.get("ip") == ip]
    if found:
        print(f"IP {ip}: name={found[0].get('name')} switch={found[0].get('switch')} vlan={found[0].get('vlan')} kind={found[0].get('kind')}")
    else:
        print(f"IP {ip}: NOT FOUND IN INVENTORY")
