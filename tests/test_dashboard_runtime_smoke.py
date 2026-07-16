from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_PY = REPO_ROOT / "scripts" / "dashboard_runtime_smoke_test.py"
SMOKE_SH = REPO_ROOT / "scripts" / "dashboard_runtime_smoke_test.sh"
DOC = REPO_ROOT / "docs" / "dashboard_runtime_validation_vi.md"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("dashboard_runtime_smoke", SMOKE_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_smoke_suite_has_required_live_cases_and_artifacts():
    source = SMOKE_PY.read_text(encoding="utf-8")
    wrapper = SMOKE_SH.read_text(encoding="utf-8")
    for case in (
        "controller_port_6653",
        "backend_port_8000",
        "frontend_port_5173",
        "mininet_topology_process",
        "agent_health_before",
        "ping_h30_to_voice",
        "ping_project_isolation",
        "udp_voice_first",
        "udp_voice_second",
        "tcp_voice",
        "voice_quality",
        "ping_after_iperf",
        "agent_health_after",
        "concurrency_different_destinations",
        "concurrency_same_destination_busy",
        "runtime_logs_no_new_unhandled_errors",
    ):
        assert case in source
    assert "runtime_reports" in source
    assert "dashboard_runtime_" in source
    assert "PASS" in source and "FAIL" in source
    assert "duration_seconds" in source
    assert "error_code" in source
    assert "response_summary" in source
    assert "sudo ./scripts/dashboard_runtime_smoke_test.sh" in wrapper


def test_smoke_suite_does_not_print_or_store_operator_token():
    source = SMOKE_PY.read_text(encoding="utf-8")
    assert 'log(TOKEN)' not in source
    assert '"token": TOKEN' not in source
    assert "X-CCH-Operator-Token" in source
    assert "gia tri token khong duoc ghi" in source


def test_smoke_suite_uses_real_commands_without_shell_true():
    source = SMOKE_PY.read_text(encoding="utf-8")
    assert "subprocess.run(command" in source
    assert "shell=True" not in source
    assert '["ovs-vsctl", "br-exists", "core_hq"]' in source
    assert '["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "core_hq"]' in source
    assert "urllib.request.urlopen" in source
    assert "json.loads" in source


def test_report_summary_removes_raw_output_and_token():
    module = load_smoke_module()
    summary = module.summarize({
        "ok": True,
        "message": "done",
        "raw": "secret raw output",
        "result": {"throughput_mbps": 12.5},
    })
    assert summary["ok"] is True
    assert summary["throughput_mbps"] == 12.5
    assert "raw" not in summary
    assert "token" not in summary


def test_runtime_document_separates_static_and_live_validation():
    content = DOC.read_text(encoding="utf-8")
    assert "Static test va live runtime test" in content
    assert "sudo ./scripts/dashboard_runtime_smoke_test.sh" in content
    assert "runtime_reports/dashboard_runtime_<timestamp>.log" in content
    assert "Khong danh dau live runtime PASS" in content


def test_live_status_exposes_active_iperf_count():
    api_source = (REPO_ROOT / "dashboard" / "backend" / "app" / "api.py").read_text(encoding="utf-8")
    live_source = (REPO_ROOT / "dashboard" / "backend" / "app" / "live_mininet.py").read_text(encoding="utf-8")
    assert "iperf_runtime_status()" in api_source
    assert '"/live/iperf-sessions"' in api_source
    assert '"active_count": len(sessions)' in live_source


def test_smoke_report_is_saved_for_preflight_failure():
    source = SMOKE_PY.read_text(encoding="utf-8")
    assert "atexit.register(save_report)" in source
    assert "REPORT_SAVED" in source
    assert "LINUX_REQUIRED" in source
    assert "TOKEN_FILE_MISSING" in source
    assert "different_destination_concurrency_case" in source
    assert "same_destination_concurrency_case" in source


def test_control_agent_errors_are_written_to_runtime_log():
    topology = (REPO_ROOT / "sdn_mpls_demo" / "topology_hybrid_sdn.py").read_text(encoding="utf-8")
    assert "mininet_control_agent.log" in topology
    assert "CONTROL_AGENT_LOG.open" in topology
    assert '"token"' not in topology.split("def _log_connection_error", 1)[1].split("def _error_code", 1)[0]
