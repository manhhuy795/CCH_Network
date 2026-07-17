import ipaddress

from scripts.common import load_vars
from scripts.validate_vars import validate_all


# NHOM A: VLAN tests assert subnet, gateway va site ownership cu the.
def test_vlan_schema_and_gateways_are_valid():
    config = load_vars()
    errors = validate_all(config)
    assert errors == []

    vlan_ids = [vlan["id"] for vlan in config["vlans"]]
    assert len(vlan_ids) == len(set(vlan_ids))

    for vlan in config["vlans"]:
        network = ipaddress.ip_network(vlan["subnet"])
        gateway = ipaddress.ip_address(vlan["gateway"])
        assert gateway in network
        assert gateway not in {network.network_address, network.broadcast_address}

    by_id = {int(vlan["id"]): vlan for vlan in config["vlans"]}
    assert by_id[50]["site"] == "branch_telesale"
    assert by_id[60]["site"] == "hq"
    assert by_id[60]["gateway"] == "172.16.60.1"
