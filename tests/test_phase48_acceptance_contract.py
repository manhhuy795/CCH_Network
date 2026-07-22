from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/phase48_final_ubuntu_acceptance.sh"
BUNDLE = ROOT / "scripts/phase48_failure_bundle.sh"

def test_phase48_gate_contract():
    text = GATE.read_text(encoding="utf-8")
    for value in ("preflight", "static", "runtime", "full", "clean-clone",
                  "--reuse-running", "--start-missing", "--report-dir",
                  "summary.json", "case_results.json", "manifest.sha256",
                  "phase46_verified", "phase47_verified"):
        assert value in text
    assert "phase49" not in text.lower()
    assert "git reset --hard" not in text
    assert "git clean" not in text
    assert "push --force" not in text

def test_failure_bundle_contract():
    text = BUNDLE.read_text(encoding="utf-8")
    for value in ("redact_text", "X-CCH-Operator-Token", "Authorization",
                  "PRIVATE KEY", ".git-credentials", "browser"):
        assert value in text
    assert "rm -rf" not in text
    assert "HOME" not in text
