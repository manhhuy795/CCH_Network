from pathlib import Path

from scripts.infrastructure_security_check import SECURITY_CASES, audit


ROOT = Path(__file__).resolve().parents[1]


def test_infrastructure_security_static_audit_passes_without_runtime_assumptions():
    results = audit()

    assert len(SECURITY_CASES) == 12
    assert all(passed for _name, passed, _detail in results)
    assert any(name == "policy: IT cannot bypass Social Media block" for name, _passed, _detail in results)
    assert any(name == "policy: Internet inbound to HQ user" for name, _passed, _detail in results)


def test_runtime_checker_uses_control_agent_ovs_and_firewall_evidence():
    source = (ROOT / "scripts" / "infrastructure_security_runtime_check.py").read_text(encoding="utf-8")
    wrapper = (ROOT / "scripts" / "infrastructure_security_runtime_check.sh").read_text(encoding="utf-8")

    assert '"PING"' in source
    assert '"FIREWALL_STATUS"' in source
    assert '"ovs-ofctl"' in source
    assert '"ovs-vsctl"' in source
    assert "social_deny" in source
    assert "inbound_deny" in source
    assert "PENDING Ubuntu runtime" in wrapper
    assert "infrastructure_security_runtime_check.py" in wrapper
    assert "shell=True" not in source


def test_security_document_separates_static_and_live_evidence():
    document = (ROOT / "docs" / "infrastructure_security_testing_vi.md").read_text(encoding="utf-8")

    assert "Kiểm tra tĩnh" in document
    assert "runtime thật" in document
    assert "Không dùng static result để tuyên bố runtime PASS" in document
