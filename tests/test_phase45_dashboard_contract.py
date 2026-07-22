from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "dashboard" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _offline_agent(monkeypatch):
    from app import live_mininet

    unavailable = {
        "ok": False,
        "available": False,
        "error_code": "MININET_NOT_RUNNING",
        "message": "Mininet chua chay.",
    }
    monkeypatch.setattr(live_mininet.mininet_control, "firewall_status", lambda: unavailable)
    monkeypatch.setattr(live_mininet.mininet_control, "get_link_status", lambda: unavailable)
    monkeypatch.setattr(live_mininet.mininet_control, "live_status", lambda: unavailable)
    return live_mininet


def test_phase45_exposes_exact_two_public_sites_and_runtime_bridge_map(monkeypatch):
    live_mininet = _offline_agent(monkeypatch)
    payload = live_mininet.topology_payload()

    assert payload["site_ids"] == ["hq", "telesale"]
    assert {site["id"] for site in payload["sites"]} == {"hq", "telesale"}
    assert next(site for site in payload["sites"] if site["id"] == "telesale")["source_id"] == "branch_telesale"
    assert len(payload["logical_switches"]) == 9
    assert payload["runtime_bridge_map"]["access_backoffice"] == "access_bo"
    assert "access_bo" not in {item["logical_name"] for item in payload["logical_switches"]}
    assert {item["logical_name"] for item in payload["ce_nodes"]} == {"ce_hq", "ce_telesale"}
    assert {item["name"] for item in payload["firewalls"]} == {"fw_hq", "fw_telesale"}
    assert payload["phase44_runtime"]["status"] == "pending"
    assert payload["phase44_runtime"]["nat_conclusion"] == "NAT REQUIREMENT NOT YET CONCLUDED"


def test_phase45_groups_keep_backoffice_at_hq_and_telesale_at_telesale(monkeypatch):
    live_mininet = _offline_agent(monkeypatch)
    hosts = {host["name"]: host for host in live_mininet.topology_payload()["hosts"]}

    assert hosts["h50_01"]["site"] == "telesale"
    assert hosts["h60_01"]["site"] == "hq"
    assert hosts["h70_01"]["site"] == "hq"


def test_phase45_policy_payload_separates_openflow_and_nftables(monkeypatch):
    live_mininet = _offline_agent(monkeypatch)
    from app import policy

    payload = policy.get_policy_payload()
    assert payload["enforcement_layers"]["openflow"]["devices"] == list(live_mininet.CONTROLLED_SWITCHES)
    assert payload["enforcement_layers"]["nftables"]["devices"] == ["fw_hq", "fw_telesale"]
    assert payload["phase44_runtime"]["status"] == "pending"
    assert {item["name"] for item in payload["firewalls"]} == {"fw_hq", "fw_telesale"}


def test_phase45_packet_path_keeps_site_enforcement_authoritative():
    from app.live_mininet import policy_decision

    backoffice_voice = policy_decision("h60_01", "h90")
    telesale_voice = policy_decision("h50_01", "h90")
    hq_call = policy_decision("h60_01", "hcall")
    telesale_call = policy_decision("h50_01", "hcall")
    project_deny = policy_decision("h20_01", "h30_01")

    assert backoffice_voice["action"] == "allow"
    assert backoffice_voice["path"] == ["backoffice", "access_backoffice", "core_hq", "voice_access", "h90"]
    assert telesale_voice["action"] == "allow"
    assert "ce_telesale" in telesale_voice["path"]
    assert "mpls_cloud" in telesale_voice["path"]
    assert "fw_hq" in hq_call["path"] and hq_call["path"][-1] == "hcall"
    assert "fw_telesale" in telesale_call["path"] and telesale_call["path"][-1] == "hcall"
    assert project_deny["action"] == "deny"
    assert project_deny["blocked_at"] == "core_hq"


def test_phase45_metrics_do_not_report_live_without_real_counters(monkeypatch):
    live_mininet = _offline_agent(monkeypatch)
    payload = live_mininet.pair_realtime_metrics("h20_01", "h90", previous_bytes=0, previous_time=1)

    assert payload["metric_state"] == "unavailable"
    assert payload["data_source"] is None
    assert payload["throughput_mbps"] is None


def test_phase45_firewall_inventory_keeps_runtime_counters_unverified(monkeypatch):
    live_mininet = _offline_agent(monkeypatch)
    inventory = live_mininet.firewall_inventory()

    assert len(inventory) == 2
    assert all(item["runtime_status"] == "unavailable" for item in inventory)
    assert all(item["counters"] is None for item in inventory)
    assert all(item["nftables_status"] == "unavailable" for item in inventory)
    assert all(item["nat"]["conclusion"] == "NAT REQUIREMENT NOT YET CONCLUDED" for item in inventory)
