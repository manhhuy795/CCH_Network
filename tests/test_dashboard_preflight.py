from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_ROOT))

from app import preflight
from scripts import mininet_dashboard_preflight as collector


PING_OK = """2 packets transmitted, 2 received, 0% packet loss, time 1001ms
rtt min/avg/max/mdev = 0.081/0.144/0.207/0.063 ms
"""
PING_BLOCKED = "2 packets transmitted, 0 received, 100% packet loss, time 1021ms\n"


def test_parse_ping_output_extracts_loss_and_average_rtt():
    assert collector.parse_ping_output(PING_OK) == {
        "packet_loss_percent": 0.0,
        "avg_rtt_ms": 0.144,
    }
    assert collector.parse_ping_output(PING_BLOCKED) == {
        "packet_loss_percent": 100.0,
        "avg_rtt_ms": None,
    }


def test_collect_report_uses_live_observations(monkeypatch):
    monkeypatch.setattr(collector, "verify_fabric", lambda: {
        "flow_counts": {"core_hq": 31, "dist_branch": 25},
        "live": {
            "hosts": {f"h{i}": True for i in range(133)},
            "user_hosts_online": 110,
        },
    })
    monkeypatch.setattr(collector, "model_hosts", lambda: {f"h{i}": {} for i in range(133)})
    monkeypatch.setattr(collector, "agent_request", lambda command: {
        "ok": command == "GET_LINK_STATUS",
        "links": {"hq-wan": "up", "wan-branch": "up"},
    })

    def fake_ping(_source: str, _destination: str, count: int = 2):
        expected = collector.CASES[len(calls)]["expected"]
        calls.append(expected)
        return {
            "ok": expected,
            "raw": PING_OK if expected else PING_BLOCKED,
            "duration_seconds": 0.1,
        }

    calls: list[bool] = []
    monkeypatch.setattr(collector, "ping", fake_ping)
    report = collector.collect_report()

    assert report["status"] == "passed"
    assert report["summary"] == {
        "checks_passed": 5,
        "checks_total": 5,
        "endpoints_online": 133,
        "endpoints_total": 133,
        "user_hosts_online": 110,
        "switches_ready": 2,
        "switches_expected": 2,
        "flow_entries": 56,
        "links_up": 2,
        "links_total": 2,
    }
    assert report["cases"][0]["avg_rtt_ms"] == 0.144
    assert report["cases"][-1]["observed"] == "blocked"


def test_backend_exposes_valid_report_and_marks_missing(monkeypatch, tmp_path):
    report_file = tmp_path / "dashboard_preflight.json"
    monkeypatch.setenv("CCH_DASHBOARD_PREFLIGHT_REPORT", str(report_file))
    assert preflight.dashboard_preflight_status()["status"] == "not_run"

    report_file.write_text(json.dumps({
        "schema_version": 1,
        "status": "passed",
        "checked_at": "2999-01-01T00:00:00+00:00",
        "summary": {"checks_passed": 5, "checks_total": 5},
        "cases": [],
    }), encoding="utf-8")
    payload = preflight.dashboard_preflight_status()
    assert payload["available"] is True
    assert payload["status"] == "passed"
    assert payload["stale"] is False
