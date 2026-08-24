from scripts.network_model import build_host_inventory, load_network_model, user_count


def test_v7_runtime_has_ninety_corporate_users():
    model = load_network_model()
    assert user_count(model) == 90
    hosts = build_host_inventory(model)
    assert sum(host["kind"] == "user" for host in hosts.values()) == 90


def test_project2_runtime_is_scaled_but_preserves_two_sites():
    model = load_network_model()
    group = model["host_groups"]["project_2"]
    assert group["count"] == 20
    assert group["design_branch_users_approx"] == 70
    assert {item["site"] for item in group["placements"]} == {"hq", "branch"}
    assert sum(item["count"] for item in group["placements"]) == 20
