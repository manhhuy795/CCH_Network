import subprocess
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/phase48_failure_bundle.sh"

def test_bundle_has_safe_cli():
    if sys.platform == "win32" or shutil.which("bash") is None:
        pytest.skip("bash is required for the Ubuntu-only failure bundle")
    result = subprocess.run(["bash", str(SCRIPT), "--help"], text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0
    assert "--report-dir" in result.stdout

def test_bundle_rejects_outside_report():
    if sys.platform == "win32" or shutil.which("bash") is None:
        pytest.skip("bash is required for the Ubuntu-only failure bundle")
    result = subprocess.run(["bash", str(SCRIPT), "--report-dir", "/tmp"],
                            text=True, capture_output=True, check=False)
    assert result.returncode != 0
