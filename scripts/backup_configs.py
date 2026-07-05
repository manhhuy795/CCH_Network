from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import BACKUPS_DIR, REPO_ROOT, load_env, load_yaml, require_confirm_deploy


def _flatten_hosts(node: dict[str, Any]) -> dict[str, dict[str, Any]]:
    hosts: dict[str, dict[str, Any]] = {}
    hosts.update(node.get("hosts", {}) or {})
    for child in (node.get("children", {}) or {}).values():
        hosts.update(_flatten_hosts(child))
    return hosts


def load_inventory(path: Path) -> dict[str, dict[str, Any]]:
    return _flatten_hosts(load_yaml(path).get("all", {}))


def netmiko_params(name: str, host: dict[str, Any]) -> dict[str, Any]:
    load_env()
    username = os.getenv("NET_USERNAME")
    password = os.getenv("NET_PASSWORD")
    secret = os.getenv("NET_SECRET", "")
    if not username or not password:
        raise SystemExit("NET_USERNAME and NET_PASSWORD must be set in environment or .env")
    return {
        "host": host["ansible_host"],
        "device_type": host.get("netmiko_device_type", "cisco_ios"),
        "username": username,
        "password": password,
        "secret": secret,
        "timeout": int(os.getenv("NET_TIMEOUT", "30")),
        "session_log": None,
        "global_delay_factor": 1,
        "conn_timeout": int(os.getenv("NET_TIMEOUT", "30")),
        "banner_timeout": int(os.getenv("NET_TIMEOUT", "30")),
        "auth_timeout": int(os.getenv("NET_TIMEOUT", "30")),
        "name": name,
    }


def backup_device(name: str, host: dict[str, Any], output_dir: Path) -> list[Path]:
    from netmiko import ConnectHandler

    output_dir.mkdir(parents=True, exist_ok=True)
    params = netmiko_params(name, host)
    device_name = params.pop("name")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    saved_files: list[Path] = []
    with ConnectHandler(**params) as connection:
        if params.get("secret"):
            connection.enable()
        for command, label in (
            ("show running-config", "running"),
            ("show startup-config", "startup"),
        ):
            output = connection.send_command(command, read_timeout=60)
            path = output_dir / f"{device_name}_{label}_{timestamp}.cfg"
            path.write_text(output.rstrip() + "\n", encoding="utf-8")
            saved_files.append(path)
    return saved_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup running/startup config with Netmiko")
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "inventories" / "lab_inventory.yml")
    parser.add_argument("--limit", nargs="*", help="Device names to backup")
    parser.add_argument("--output-dir", type=Path, default=BACKUPS_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Only print selected devices")
    args = parser.parse_args()

    hosts = load_inventory(args.inventory)
    selected = {name: data for name, data in hosts.items() if not args.limit or name in args.limit}
    if args.dry_run:
        print("Backup dry-run. Selected devices:")
        for name, data in selected.items():
            print(f"- {name} ({data.get('ansible_host')})")
        return 0

    require_confirm_deploy("connect to devices for backup")
    for name, data in selected.items():
        files = backup_device(name, data, args.output_dir)
        for path in files:
            print(f"Saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
