import ipaddress
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".j2", ".cfg", ".txt", ".json"}


def test_primary_sources_do_not_use_old_non_private_plan():
    checked_roots = ["vars", "templates", "scripts", "docs", "generated_configs", "sdn_demo", "sdn_mpls_demo"]
    violations = []

    for root_name in checked_roots:
        for path in (REPO_ROOT / root_name).rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                if "172.10." in path.read_text(encoding="utf-8", errors="ignore"):
                    violations.append(str(path.relative_to(REPO_ROOT)))

    assert violations == []


def test_vlan_networks_use_private_ipv4_space():
    data = yaml.safe_load((REPO_ROOT / "vars" / "vlans.yml").read_text(encoding="utf-8"))
    expected = {
        20: "172.16.20.0/24",
        30: "172.16.30.0/24",
        40: "172.16.40.0/24",
        50: "172.16.50.0/24",
        60: "172.16.60.0/24",
        90: "172.16.90.0/24",
    }
    by_id = {int(item["id"]): item for item in data["vlans"]}

    for vlan_id, subnet in expected.items():
        network = ipaddress.ip_network(by_id[vlan_id]["subnet"])
        assert str(network) == subnet
        assert network.is_private
