from __future__ import annotations

import importlib.util
import signal
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/phase46_automation_docs_gate.py"
SPEC = importlib.util.spec_from_file_location("phase46_gate", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_required_gate_and_documentation_files_exist():
    assert (ROOT / "scripts/phase46_automation_docs_gate.sh").is_file()
    for relative in MODULE.REQUIRED_DOCS:
        assert (ROOT / relative).is_file()


def test_missing_binary_and_wrong_python_are_not_pass():
    assert MODULE.command_available("command-that-does-not-exist-phase46") is False
    compatible, _version = MODULE.python_is_compatible("/bin/sh")
    assert compatible is False


def test_port_parser_and_stale_socket_detection():
    ports = MODULE.parse_listening_ports("LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*\n")
    assert 8000 in ports
    path = Path("/tmp/phase46-stale-socket-test.sock")
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.close()
    try:
        assert MODULE.is_stale_socket(path, "test-token") is True
    finally:
        path.unlink()


def test_summary_schema_and_first_failure():
    payload = MODULE.summary_payload(
        "static",
        "feature/phase46-automation-docs",
        "abc1234",
        [{"name": "first", "status": "BLOCKED", "exit_code": 127}, {"name": "later", "status": "PASS", "exit_code": 0}],
        Path("/tmp/phase46-report"),
    )
    assert payload["overall_status"] == "BLOCKED"
    assert payload["first_failure"]["name"] == "first"


def test_no_fake_pass_on_skip_and_secrets_are_redacted():
    payload = MODULE.summary_payload("runtime", "branch", "head", [{"name": "skip", "status": "BLOCKED", "exit_code": 3}], Path("/tmp/phase46-report"))
    assert payload["overall_status"] != "PASS"
    assert MODULE.redact("operator-secret-output", ["operator-secret-output"]) == "[REDACTED]"


def test_safe_stop_only_terminates_owned_process():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], text=True)
    try:
        stopped = MODULE.safe_stop([process])
        assert process.pid in stopped
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=3)


def test_gate_uses_no_shell_true_or_broad_cleanup():
    source = PATH.read_text(encoding="utf-8")
    assert "shell=True" not in source
    assert "pkill" not in source
    assert "killall" not in source
    assert "mn -c" not in source


def test_documentation_reference_checker_detects_missing_link(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text("[missing](missing.md)\n", encoding="utf-8")
    assert MODULE.docs_reference_errors(tmp_path) == ["docs/index.md -> missing.md"]

