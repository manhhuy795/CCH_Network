from __future__ import annotations

import json
import os
import shutil
import socket
import time
from pathlib import Path
from typing import Any

import yaml

from . import live_mininet
from sdn_mpls_demo.policy_engine import PolicyEngine


ADMIN_SOCKET = Path(os.environ.get("CCH_OSKEN_ADMIN_SOCKET", "/tmp/cch_osken_admin.sock"))
ADMIN_TOKEN = os.environ.get("CCH_OSKEN_ADMIN_TOKEN", "cch-local-admin-token")
POLICY_FILE = live_mininet.POLICY_FILE
POLICY_BACKUP_DIR = POLICY_FILE.parent / "runtime" / "policy_backups"


def get_policy_payload() -> dict:
    return live_mininet.policy_payload()


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


def toggle_policy(key: str, enabled: bool) -> dict[str, Any]:
    payload = _load_policy_file()
    policies = payload.get("policies", {})
    if key not in policies or not isinstance(policies[key], bool):
        raise KeyError(f"Khong co boolean policy: {key}")

    old_value = policies[key]
    policies[key] = enabled
    backup_path = _atomic_write_policy(payload)
    reload_result = _controller_reload()
    if not reload_result.get("ok"):
        _restore_policy(backup_path)
        live_mininet.reload_policy_engine()
        return {
            "ok": False,
            "message": "Policy reload that bai, da rollback policy.yml. Flow cu duoc giu nguyen tren controller.",
            "error": reload_result.get("message", "Khong ro loi controller."),
            "policies": _load_policy_file()["policies"],
        }

    live_mininet.reload_policy_engine()
    return {
        "ok": True,
        "message": "Policy da ap dung.",
        "changed": {"key": key, "old": old_value, "new": enabled},
        "backup": str(backup_path),
        "reload": reload_result,
        "policies": _load_policy_file()["policies"],
    }
