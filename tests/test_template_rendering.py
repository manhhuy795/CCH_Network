from pathlib import Path

from scripts.generate_configs import generate_configs


# NHOM A: generator test assert noi dung interface, VLAN, route va uplink cu the.
def test_render_config_outputs_expected_files_and_logic(tmp_path: Path):
    rendered = generate_configs(tmp_path)
    names = {path.name for path in rendered}

    assert "hq-core-l3.cfg" in names
    assert "hq-ce-router.cfg" in names
    assert "br-ce-router.cfg" in names
    assert "hq-firewall.policy.txt" in names
    assert "hq-backoffice-access.cfg" in names
    assert "hq-access-it.cfg" in names

    hq_core = (tmp_path / "hq-core-l3.cfg").read_text(encoding="utf-8")
    assert "interface Vlan20" in hq_core
    assert "ip access-list extended ACL_VLAN20_IN" in hq_core
    assert "deny ip 172.16.20.0 0.0.0.255 172.16.30.0 0.0.0.255 log" in hq_core
    assert "ip route 0.0.0.0 0.0.0.0 10.10.254.2" in hq_core

    hq_ce = (tmp_path / "hq-ce-router.cfg").read_text(encoding="utf-8")
    assert "ip route 172.16.50.0 255.255.255.0 10.255.0.2" in hq_ce
    assert "203.0.113.1" not in hq_ce

    backoffice_access = (tmp_path / "hq-backoffice-access.cfg").read_text(encoding="utf-8")
    assert "interface range GigabitEthernet1/0/1-48" in backoffice_access
    assert "switchport access vlan 60" in backoffice_access
    assert "switchport trunk allowed vlan 10,60" in backoffice_access

    it_access = (tmp_path / "hq-access-it.cfg").read_text(encoding="utf-8")
    assert "interface range GigabitEthernet1/0/1-48" in it_access
    assert "switchport access vlan 70" in it_access
    assert "switchport trunk allowed vlan 10,70" in it_access
