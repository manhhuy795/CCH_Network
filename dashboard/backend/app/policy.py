from __future__ import annotations

import json
import os
import shutil
import socket
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import live_mininet
from sdn_mpls_demo.policy_engine import PolicyEngine


ADMIN_SOCKET = Path(os.environ.get("CCH_OSKEN_ADMIN_SOCKET", "/tmp/cch_osken_admin.sock"))
ADMIN_TOKEN = os.environ.get("CCH_OSKEN_ADMIN_TOKEN", "cch-local-admin-token")
POLICY_FILE = live_mininet.POLICY_FILE
POLICY_BACKUP_DIR = POLICY_FILE.parent / "runtime" / "policy_backups"
POLICY_STATUS_FILE = POLICY_FILE.parent / "runtime" / "policy_apply_status.json"
FIREWALL_POLICY_KEYS = {
    "allow_zalo",
    "allow_call_app",
    "allow_general_internet",
    "block_social_media",
}

POLICY_CATALOG: dict[str, dict[str, Any]] = {
    "isolate_hq_projects": {
        "name": "Cô lập các dự án tại HQ",
        "description": "Cô lập lưu lượng ngang giữa VLAN dự án A, B và C tại HQ.",
        "source": "VLAN 20 / 30 / 40",
        "destination": "VLAN dự án khác tại HQ",
        "action": "DROP",
        "enforcement_point": "core_hq",
        "priority": 400,
        "cookie": "0x1001",
    },
    "isolate_telesale_backoffice": {
        "name": "Cô lập VLAN 50 và VLAN 60",
        "description": "Cô lập hai chiều giữa Telesale VLAN 50 và BackOffice VLAN 60 tại HQ.",
        "source": "VLAN 50 / 60",
        "destination": "VLAN 60 / 50",
        "action": "DROP",
        "enforcement_point": "dist_telesale / core_hq theo chieu nguon",
        "priority": 400,
        "cookie": "0x1002",
    },
    "allow_voice": {
        "name": "Cho phép dịch vụ Voice",
        "description": "Cho phép các VLAN nghiệp vụ truy cập PBX/SBC Voice Service.",
        "source": "VLAN 20 / 30 / 40 / 50 / 60 / 70",
        "destination": "h90 · Voice Service",
        "action": "ALLOW",
        "enforcement_point": "core_hq / dist_telesale",
        "priority": 425,
        "cookie": "0x1200",
    },
    "allow_zalo": {
        "name": "Cho phép Zalo",
        "description": "Cho phép truy cập dịch vụ Zalo qua Internet Edge phù hợp từng site.",
        "source": "User VLAN được cấp quyền",
        "destination": "hzalo",
        "action": "ALLOW",
        "enforcement_point": "fw_hq / fw_telesale (nftables)",
        "priority": 0,
        "cookie": "n/a",
    },
    "allow_call_app": {
        "name": "Cho phép Call App / CRM",
        "description": "Cho phép truy cập Call App/CRM phục vụ nghiệp vụ.",
        "source": "User VLAN được cấp quyền",
        "destination": "hcall",
        "action": "ALLOW",
        "enforcement_point": "fw_hq / fw_telesale (nftables)",
        "priority": 0,
        "cookie": "n/a",
    },
    "allow_general_internet": {
        "name": "Cho phép Internet thông thường",
        "description": "Cho phép lưu lượng Internet mô phỏng đi qua Firewall của site.",
        "source": "User VLAN được cấp quyền",
        "destination": "hinternet",
        "action": "ALLOW",
        "enforcement_point": "fw_hq / fw_telesale (nftables)",
        "priority": 0,
        "cookie": "n/a",
    },
    "block_social_media": {
        "name": "Chặn Social Media",
        "description": "Chặn Social Media đối với user nghiệp vụ và IT Support.",
        "source": "VLAN 20 / 30 / 40 / 50 / 60 / 70",
        "destination": "hsocial",
        "action": "DROP",
        "enforcement_point": "fw_hq / fw_telesale (nftables)",
        "priority": 0,
        "cookie": "n/a",
    },
    "allow_it_support_controlled_access": {
        "name": "IT Support truy cập có kiểm soát",
        "description": "Cho phép IT Support quản trị user theo least privilege, không mở truy cập ngược.",
        "source": "VLAN 70 · IT Support",
        "destination": "Managed user VLAN và dịch vụ được phép",
        "action": "ALLOW",
        "enforcement_point": "core_hq",
        "priority": 450,
        "cookie": "0x1301",
    },
    "voice_flow_priority": {
        "name": "Ưu tiên luồng Voice",
        "description": "Ưu tiên flow policy Voice cao hơn các flow dịch vụ thông thường.",
        "source": "User VLAN được cấp quyền",
        "destination": "h90 · Voice Service",
        "action": "ALLOW",
        "enforcement_point": "core_hq / dist_telesale",
        "priority": 425,
        "cookie": "0x1200",
    },
    "intersite_via_mpls_l3vpn": {
        "name": "Liên site qua MPLS L3VPN Logic",
        "description": "Định tuyến logic liên site qua MPLS L3VPN Cloud; không program PE/P.",
        "source": "HQ / Telesale được policy cho phép",
        "destination": "Site đối diện",
        "action": "ALLOW",
        "enforcement_point": "core_hq / dist_telesale",
        "priority": 180,
        "cookie": "0x1100",
    },
}


def get_policy_payload() -> dict:
    payload = live_mininet.policy_payload()
    payload["inventory"] = policy_inventory(payload.get("policies", {}))
    payload["enforcement_layers"] = {
        "openflow": {
            "engine": "OpenFlow 1.3",
            "devices": list(live_mininet.CONTROLLED_SWITCHES),
            "responsibilities": [
                "Cô lập Project A/B/C",
                "Chặn Telesale → BackOffice tại dist_telesale",
                "Chặn BackOffice → Telesale tại core_hq",
            ],
        },
        "nftables": {
            "engine": "stateful nftables",
            "devices": ["fw_hq", "fw_telesale"],
            "responsibilities": [
                "Internet filtering tại hai firewall",
                "Call App/Zalo ALLOW và Social DENY",
                "Inbound Internet DENY và established,related ALLOW",
            ],
        },
    }
    payload["firewalls"] = live_mininet.firewall_inventory()
    payload["phase44_runtime"] = live_mininet.phase44_runtime_status()
    return payload


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_hash() -> str:
    return hashlib.sha256(POLICY_FILE.read_bytes()).hexdigest()


def _read_apply_status() -> dict[str, Any]:
    try:
        payload = json.loads(POLICY_STATUS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_apply_status(payload: dict[str, Any]) -> None:
    POLICY_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_path = POLICY_STATUS_FILE.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(POLICY_STATUS_FILE)


def policy_inventory(policies: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    configured = policies if policies is not None else _load_policy_file().get("policies", {})
    status = _read_apply_status()
    current_hash = _policy_hash()
    status_matches = status.get("policy_hash") == current_hash
    controller_acknowledged = bool(
        status_matches
        and status.get("controller_acknowledged")
        and status.get("status") == "Applied"
        and ADMIN_SOCKET.exists()
    )
    updated_at = datetime.fromtimestamp(POLICY_FILE.stat().st_mtime, timezone.utc).isoformat()
    items: list[dict[str, Any]] = []
    for key, metadata in POLICY_CATALOG.items():
        value = configured.get(key)
        enforcement_engine = "nftables" if key in FIREWALL_POLICY_KEYS else "openflow"
        firewall_acknowledged = bool(
            status_matches
            and status.get("firewall_acknowledged")
            and status.get("status") == "Applied"
        )
        runtime_acknowledged = controller_acknowledged and (
            enforcement_engine != "nftables" or firewall_acknowledged
        )
        lifecycle = "Applied" if runtime_acknowledged else "Out of sync"
        if status_matches and status.get("status") == "Failed" and status.get("policy_key") == key:
            lifecycle = "Failed"
        if value is None:
            lifecycle = "Draft"
        items.append({
            "key": key,
            "name": key.replace("_", " ").title(),
            **metadata,
            "enabled": value if isinstance(value, bool) else None,
            "configuration_status": "Enabled" if value is True else "Disabled" if value is False else "Draft",
            "lifecycle_status": lifecycle,
            "enforcement_engine": enforcement_engine,
            "controller_acknowledged": controller_acknowledged,
            "firewall_acknowledged": firewall_acknowledged,
            "runtime_acknowledged": runtime_acknowledged,
            "updated_at": status.get("updated_at") if status_matches else updated_at,
            "technical_detail": status.get("technical_detail") if status_matches and status.get("policy_key") == key else None,
        })
    return items


def _load_policy_file() -> dict[str, Any]:
    return yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))


def _validate_policy_payload(payload: dict[str, Any], temp_path: Path) -> None:
    if not isinstance(payload.get("policies"), dict):
        raise ValueError("policy.yml thieu block policies.")
    temp_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    parsed = yaml.safe_load(temp_path.read_text(encoding="utf-8"))
    if parsed != payload:
        raise ValueError("policy.yml sau khi ghi tam khong khop payload.")
    PolicyEngine(temp_path)


def _atomic_write_policy(payload: dict[str, Any]) -> Path:
    POLICY_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = POLICY_BACKUP_DIR / f"policy-{timestamp}.yml"
    temp_path = POLICY_FILE.with_suffix(".yml.tmp")
    shutil.copy2(POLICY_FILE, backup_path)
    _validate_policy_payload(payload, temp_path)
    temp_path.replace(POLICY_FILE)
    return backup_path


def _restore_policy(backup_path: Path) -> None:
    shutil.copy2(backup_path, POLICY_FILE)


def _controller_reload(timeout: float = 8.0) -> dict[str, Any]:
    if not hasattr(socket, "AF_UNIX"):
        return {"ok": False, "message": "Unix Domain Socket khong kha dung tren host nay."}
    if not ADMIN_SOCKET.exists():
        return {"ok": False, "message": "Controller admin socket chua san sang. Hay chay OS-Ken controller truoc."}
    request = {"token": ADMIN_TOKEN, "action": "reload_policy"}
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(ADMIN_SOCKET))
        client.sendall(json.dumps(request).encode("utf-8"))
        response = client.recv(65536).decode("utf-8")
    finally:
        client.close()
    return json.loads(response)


def _firewall_reload() -> dict[str, Any]:
    return live_mininet.mininet_control.reload_firewall()


def _rollback_runtime(backup_path: Path, reload_firewall: bool) -> dict[str, Any]:
    _restore_policy(backup_path)
    live_mininet.reload_policy_engine()
    controller_result = _controller_reload()
    firewall_result = _firewall_reload() if reload_firewall else {"ok": True, "skipped": True}
    return {
        "controller": controller_result,
        "firewall": firewall_result,
        "ok": bool(controller_result.get("ok") and firewall_result.get("ok")),
    }


def toggle_policy(key: str, enabled: bool) -> dict[str, Any]:
    payload = _load_policy_file()
    policies = payload.get("policies", {})
    if key not in policies or not isinstance(policies[key], bool):
        raise KeyError(f"Khong co boolean policy: {key}")

    old_value = policies[key]
    policies[key] = enabled
    backup_path = _atomic_write_policy(payload)
    _write_apply_status({
        "status": "Applying",
        "policy_key": key,
        "controller_acknowledged": False,
        "policy_hash": _policy_hash(),
        "updated_at": _now_iso(),
    })
    requires_firewall = key in FIREWALL_POLICY_KEYS
    controller_result = _controller_reload()
    firewall_result = (
        _firewall_reload()
        if controller_result.get("ok") and requires_firewall
        else {"ok": True, "skipped": True}
    )
    if not controller_result.get("ok") or not firewall_result.get("ok"):
        rollback_result = _rollback_runtime(backup_path, requires_firewall)
        failure = controller_result if not controller_result.get("ok") else firewall_result
        _write_apply_status({
            "status": "Failed",
            "policy_key": key,
            "controller_acknowledged": False,
            "firewall_acknowledged": False,
            "policy_hash": _policy_hash(),
            "updated_at": _now_iso(),
            "technical_detail": {
                "failure": failure,
                "rollback": rollback_result,
            },
        })
        return {
            "ok": False,
            "message": "Policy reload that bai, da rollback policy.yml va runtime enforcement.",
            "error": failure.get("message", "Khong ro loi runtime enforcement."),
            "status": "Failed",
            "controller_acknowledged": False,
            "firewall_acknowledged": False,
            "rollback": rollback_result,
            "policies": _load_policy_file()["policies"],
        }

    live_mininet.reload_policy_engine()
    _write_apply_status({
        "status": "Applied",
        "policy_key": key,
        "controller_acknowledged": True,
        "firewall_acknowledged": bool(firewall_result.get("ok") and requires_firewall),
        "policy_hash": _policy_hash(),
        "updated_at": _now_iso(),
        "technical_detail": {
            "controller": controller_result,
            "firewall": firewall_result,
        },
    })
    return {
        "ok": True,
        "message": "Policy da ap dung tren dung runtime enforcement.",
        "status": "Applied",
        "controller_acknowledged": True,
        "firewall_acknowledged": bool(firewall_result.get("ok") and requires_firewall),
        "enforcement_engine": "nftables" if requires_firewall else "openflow",
        "changed": {"key": key, "old": old_value, "new": enabled},
        "backup": str(backup_path),
        "reload": {
            "controller": controller_result,
            "firewall": firewall_result,
        },
        "policies": _load_policy_file()["policies"],
    }
