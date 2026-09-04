from dashboard.backend.app.policy import FIREWALL_POLICY_KEYS, POLICY_CATALOG


def test_policy_catalog_matches_v7_runtime_enforcement():
    assert set(POLICY_CATALOG) == {
        "isolate_hq_projects",
        "allow_voice",
        "voice_flow_priority",
        "allow_zalo",
        "allow_call_app",
        "allow_general_internet",
        "allow_guest_general_internet",
        "block_social_media",
        "allow_it_support_controlled_access",
    }
    assert POLICY_CATALOG["isolate_hq_projects"]["source"] == "VLAN 101 / 93 / 103 / 104"
    assert POLICY_CATALOG["block_social_media"]["source"] == "Managed user VLAN / VLAN 110 IT Support"
    assert POLICY_CATALOG["allow_it_support_controlled_access"]["source"] == "VLAN 110 · IT Support"
    assert FIREWALL_POLICY_KEYS.issubset(POLICY_CATALOG)
