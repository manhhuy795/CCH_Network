from scripts.phase42_namespace_inventory import (
    EXPECTED_INFRA_NAMESPACES,
    EXPECTED_ENTERPRISE_ENDPOINTS,
    EXPECTED_SERVICES,
    EXPECTED_USERS,
    classify_live_namespaces,
    extract_live_namespaces,
    render_report,
)


# NHOM A: these tests enforce the live namespace acceptance contract.
def process_lines(names, duplicate_names=()):
    all_names = [*names, *duplicate_names]
    return [f"bash --norc --noediting -is mininet:{name}\n" for name in all_names]


def valid_live_names():
    return {
        *EXPECTED_USERS,
        *EXPECTED_SERVICES,
        *EXPECTED_INFRA_NAMESPACES,
        *EXPECTED_ENTERPRISE_ENDPOINTS,
        "hq_l3_gateway",
        "telesale_l3_gateway",
        "service_net",
        "access_floor1",
        "core_hq",
    }


def test_exact_service_user_and_infrastructure_sets_ignore_duplicate_processes():
    lines = process_lines(valid_live_names(), duplicate_names=("h90", "hcall", "ce_hq", "h20_01"))
    extracted = extract_live_namespaces(lines)
    inventory = classify_live_namespaces(extracted)

    assert len(extracted) < len(lines)
    assert inventory["users"] == EXPECTED_USERS
    assert len(inventory["users"]) == 110
    assert inventory["services"] == EXPECTED_SERVICES
    assert len(inventory["services"]) == 5
    assert inventory["infrastructure"] == EXPECTED_INFRA_NAMESPACES
    assert len(inventory["infrastructure"]) == 16
    assert inventory["enterprise"] == EXPECTED_ENTERPRISE_ENDPOINTS
    assert "h90" in inventory["services"]
    assert "h90" not in inventory["users"]
    for non_service in (*EXPECTED_INFRA_NAMESPACES, "service_net"):
        assert non_service not in inventory["services"]


def test_valid_inventory_report_prints_exact_counts_and_passes(capsys):
    lines = process_lines(valid_live_names(), duplicate_names=("h90", "ce_hq"))

    assert render_report(lines) is True

    output = capsys.readouterr().out
    assert "USER_NAMESPACE_COUNT=110" in output
    assert "SERVICE_NAMESPACE_COUNT=5" in output
    assert "INFRA_NAMESPACE_COUNT=16" in output
    assert "ENTERPRISE_NAMESPACE_COUNT=9" in output
    assert "ACTUAL_SERVICE_NAMES=h90 hcall hinternet hsocial hzalo" in output
    assert "ACTUAL_INFRA_NAMES=ce_hq ce_telesale fw_hq fw_telesale had hbackup hdhcp hdialer hdns hmonitor hntp hnvr hrecording internet_zone mpls_backup mpls_primary" in output
    assert "PASS Dung 110 user namespace" in output
    assert "PASS Dung 5 service namespace" in output
    assert "PASS Dung 16 infra namespace" in output
    assert "PASS Dung 9 enterprise namespace" in output


def test_missing_service_fails_and_prints_exact_name(capsys):
    names = valid_live_names() - {"hsocial"}

    assert render_report(process_lines(names)) is False

    output = capsys.readouterr().out
    assert "SERVICE_NAMESPACE_COUNT=4" in output
    assert "MISSING_SERVICE_NAMES=hsocial" in output
    assert "UNEXPECTED_SERVICE_NAMES=" in output
    assert "FAIL SERVICE namespace set mismatch" in output


def test_unexpected_service_fails_and_prints_exact_name(capsys):
    names = valid_live_names() | {"hunknown"}

    assert render_report(process_lines(names)) is False

    output = capsys.readouterr().out
    assert "SERVICE_NAMESPACE_COUNT=6" in output
    assert "MISSING_SERVICE_NAMES=" in output
    assert "UNEXPECTED_SERVICE_NAMES=hunknown" in output
    assert "FAIL SERVICE namespace set mismatch" in output


def test_resource_gate_uses_unique_inventory_helper_not_pgrep_counts():
    from pathlib import Path

    gate = Path("scripts/phase42_resource_gate.sh").read_text(encoding="utf-8")

    assert 'ps -eo args= | python3 "$ROOT_DIR/scripts/phase42_namespace_inventory.py"' in gate
    assert "EXIT_CODE_NAMESPACE_INVENTORY" in gate
    assert "pgrep -af 'mininet:h(20|30|40|50|60|70)" not in gate
    assert "pgrep -af 'mininet:(h90|hzalo|hcall|hsocial|hinternet)" not in gate
