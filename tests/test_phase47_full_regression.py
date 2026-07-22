from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "phase47_full_regression_gate.sh"
MATRIX = ROOT / "docs" / "phase47_regression_matrix.md"
PHASE44 = ROOT / "scripts" / "phase44_firewall_runtime_check.py"
SPEC = importlib.util.spec_from_file_location("phase44_firewall_runtime_check", PHASE44)
assert SPEC and SPEC.loader
PHASE44_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PHASE44_MODULE
SPEC.loader.exec_module(PHASE44_MODULE)


def test_phase47_gate_has_required_modes_and_options():
    text = GATE.read_text(encoding="utf-8")
    for mode in ("preflight", "source", "static", "frontend", "automation", "runtime", "full"):
        assert mode in text
    for option in ("--reuse-running", "--start-missing", "--report-dir", "--case"):
        assert option in text


def test_phase47_gate_does_not_reset_or_force_push():
    text = GATE.read_text(encoding="utf-8")
    for forbidden in ("git reset --hard", "git clean", "git push --force", "git push --force-with-lease"):
        assert forbidden not in text


def test_phase47_matrix_covers_all_regression_layers():
    text = MATRIX.read_text(encoding="utf-8")
    for layer in ("Git/source", "Source of truth", "Static", "Frontend", "Phase 46", "Topology", "SDN/OpenFlow", "Firewall", "Dashboard/API", "Traffic", "Resilience", "Process hygiene", "Documentation"):
        assert f"| {layer} |" in text


def test_phase47_matrix_contains_live_acceptance_cases():
    text = MATRIX.read_text(encoding="utf-8")
    for case_id in ("F05", "F07", "G01", "G04", "G05", "H01", "I01", "J01", "J04", "J08", "K01", "K02"):
        assert f"| {case_id} |" in text


def test_phase47_precommit_checkpoint_allows_only_phase47_files():
    status = """ M scripts/phase44_firewall_runtime_check.py
?? docs/phase47_regression_matrix.md
?? scripts/phase47_full_regression_gate.sh
?? tests/test_phase47_full_regression.py
"""
    assert PHASE44_MODULE.runtime_worktree_is_acceptable(
        "feature/phase47-full-regression", status
    )
    assert not PHASE44_MODULE.runtime_worktree_is_acceptable(
        "feature/phase47-full-regression", status + "?? README.md\n"
    )
    assert not PHASE44_MODULE.runtime_worktree_is_acceptable(
        "feature/phase46-automation-docs", " M README.md\n"
    )
    assert PHASE44_MODULE.runtime_worktree_is_acceptable(
        "feature/phase46-automation-docs", ""
    )
