from pathlib import Path

from scripts.generate_configs import generate_configs


def test_render_config_outputs_expected_files_and_logic(tmp_path: Path):
    rendered = generate_configs(tmp_path)
    names = {path.name for path in rendered}

    assert "hq-core-l3.cfg" in names
    assert "hq-ce-router.cfg" in names
    assert "br-ce-router.cfg" in names
    assert "hq-firewall.policy.txt" in names

    hq_core = (tmp_path / "hq-core-l3.cfg").read_text(encoding="utf-8")
    assert "interface Vlan20" in hq_core
    assert "ip access-list extended ACL_VLAN20_IN" in hq_core
    assert "deny ip 172.10.20.0 0.0.0.255 172.10.30.0 0.0.0.255 log" in hq_core
    assert "ip route 0.0.0.0 0.0.0.0 10.10.254.2" in hq_core

    hq_ce = (tmp_path / "hq-ce-router.cfg").read_text(encoding="utf-8")
    assert "ip route 172.10.50.0 255.255.255.0 203.0.113.1" in hq_ce
    assert "198.51.100.2" not in hq_ce
