from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_each_business_group_has_twenty_users():
    data = yaml.safe_load((REPO_ROOT / "vars" / "vlans.yml").read_text(encoding="utf-8"))
    by_id = {int(item["id"]): item for item in data["vlans"]}

    for vlan_id in (20, 30, 40, 50, 60):
        assert by_id[vlan_id]["approx_users"] == 20
    assert by_id[70]["approx_users"] == 4

    assert sum(by_id[vlan_id]["approx_users"] for vlan_id in (20, 30, 40, 50, 60, 70)) == 104
