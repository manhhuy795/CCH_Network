from scripts.network_model import load_network_model


def test_branch_contains_only_telesale_and_iot_roles():
    model = load_network_model()
    branch_groups = {
        name for name, group in model["host_groups"].items()
        if group.get("site") == "branch_telesale"
    }
    assert branch_groups == {"telesale", "iot_branch"}
    assert "backoffice" not in branch_groups
    assert "branch_backoffice" not in model["sites"]


def test_branch_has_its_own_access_distribution_ce_and_firewall():
    model = load_network_model()
    branch_nodes = {
        name for name, node in model["switches"].items()
        if node.get("site") == "branch_telesale"
    }
    branch_infra = {
        name for name, node in model["infrastructure"].items()
        if node.get("site") == "branch_telesale"
    }
    assert branch_nodes == {"access_branch", "dist_branch"}
    assert {"ce_telesale", "fw_telesale"} <= branch_infra
