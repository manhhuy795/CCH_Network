from pathlib import Path


def test_policy_inventory_requires_controller_acknowledgement(monkeypatch, tmp_path):
    from dashboard.backend.app import policy

    source_policy = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"
    test_policy = tmp_path / "policy.yml"
    test_policy.write_text(source_policy.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(policy, "POLICY_FILE", test_policy)
    monkeypatch.setattr(policy, "POLICY_STATUS_FILE", tmp_path / "policy_apply_status.json")
    monkeypatch.setattr(policy, "ADMIN_SOCKET", tmp_path / "missing-controller.sock")

    inventory = policy.policy_inventory()
    social = next(item for item in inventory if item["key"] == "block_social_media")

    assert social["lifecycle_status"] == "Out of sync"
    assert social["controller_acknowledged"] is False
    for field in ("name", "description", "source", "destination", "action", "enforcement_point", "priority", "cookie", "configuration_status", "updated_at"):
        assert field in social


def test_successful_reload_records_applied_only_with_controller_ack(monkeypatch, tmp_path):
    from dashboard.backend.app import policy

    source_policy = Path(__file__).resolve().parents[1] / "sdn_mpls_demo" / "policy.yml"
    test_policy = tmp_path / "policy.yml"
    test_policy.write_text(source_policy.read_text(encoding="utf-8"), encoding="utf-8")
    controller_socket = tmp_path / "controller.sock"
    controller_socket.touch()
    monkeypatch.setattr(policy, "POLICY_FILE", test_policy)
    monkeypatch.setattr(policy, "POLICY_BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(policy, "POLICY_STATUS_FILE", tmp_path / "policy_apply_status.json")
    monkeypatch.setattr(policy, "ADMIN_SOCKET", controller_socket)
    monkeypatch.setattr(policy.live_mininet, "reload_policy_engine", lambda: None)
    monkeypatch.setattr(policy, "_controller_reload", lambda: {"ok": True, "switches_updated": ["core_hq"], "flows_installed": 4})
    monkeypatch.setattr(policy, "_firewall_reload", lambda: {"ok": True, "rules_applied": 1})

    current = policy._load_policy_file()["policies"]["block_social_media"]
    result = policy.toggle_policy("block_social_media", not current)
    inventory = policy.policy_inventory(result["policies"])
    social = next(item for item in inventory if item["key"] == "block_social_media")

    assert result["status"] == "Applied"
    assert result["controller_acknowledged"] is True
    assert social["lifecycle_status"] == "Applied"
    assert social["controller_acknowledged"] is True


def test_ping_path_stops_before_a_real_down_link(monkeypatch):
    from dashboard.backend.app import live_mininet

    monkeypatch.setattr(
        live_mininet.mininet_control,
        "first_down_link",
        lambda _path: {"link_id": "core_hq-voice_access", "blocked_at": "core_hq"},
    )
    monkeypatch.setattr(
        live_mininet.mininet_control,
        "ping_detailed",
        lambda *_args: {
            "ok": False,
            "raw": "3 packets transmitted, 0 received, 100% packet loss",
        },
    )

    result = live_mininet.ping("h20_01", "h90")

    assert result["ok"] is False
    assert result["decision"]["failed_link"] == "core_hq-voice_access"
    assert result["decision"]["blocked_at"] == "core_hq"
    assert result["decision"]["path"][-1] == "core_hq"
    assert "voice_access" not in result["decision"]["path"]
