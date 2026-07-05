from scripts.common import load_vars


def test_hq_project_vlans_have_required_isolation_acl():
    config = load_vars()
    policies = {policy["source_vlan"]: policy for policy in config["hq_project_isolation"]}

    assert set(policies[20]["deny_destination_vlans"]) >= {30, 40}
    assert set(policies[30]["deny_destination_vlans"]) >= {20, 40}
    assert set(policies[40]["deny_destination_vlans"]) >= {20, 30}

    for vlan_id in (20, 30, 40):
        assert 90 in policies[vlan_id]["allow_destination_vlans"]
        assert policies[vlan_id]["allow_internet"] is True


def test_branch_vlans_have_separate_policies():
    config = load_vars()
    policies = {policy["source_vlan"]: policy for policy in config["branch_policies"]}

    assert set(policies) == {50, 60}
    assert 60 in policies[50]["deny_destination_vlans"]
    assert 50 in policies[60]["deny_destination_vlans"]
