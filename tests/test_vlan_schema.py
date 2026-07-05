import ipaddress

from scripts.common import load_vars
from scripts.validate_vars import validate_all


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
