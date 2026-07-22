from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

PATH = Path(__file__).resolve().parents[1] / "scripts" / "ubuntu_phase44_45_deep_debug.py"
SPEC = importlib.util.spec_from_file_location("ubuntu_phase44_45_deep_debug", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_transfer_branch_allowed():
    assert MODULE.branch_allowed("transfer/phase45-regression-fix")


def test_unrelated_branch_rejected():
    assert not MODULE.branch_allowed("main")


def test_clean_checkpoint_passes():
    result = MODULE.evaluate_checkpoint(True, "transfer/phase45-regression-fix", "abc", True, True)
    assert result["final_checkpoint_result"] is True
    assert result["failure_reasons"] == []


def test_dirty_tree_has_specific_reason():
    result = MODULE.evaluate_checkpoint(True, "transfer/phase45-regression-fix", "abc", False, True)
    assert result["final_checkpoint_result"] is False
    assert "DIRTY_WORKTREE" in result["failure_reasons"]


def test_missing_ancestor_is_separate_failure():
    result = MODULE.evaluate_checkpoint(True, "transfer/phase45-regression-fix", "abc", True, False)
    assert result["final_checkpoint_result"] is False
    assert "REQUIRED_ANCESTOR_MISSING" in result["failure_reasons"]
