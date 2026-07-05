from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.backup_configs import load_inventory, netmiko_params
from scripts.common import BACKUPS_DIR, REPO_ROOT, require_confirm_deploy


def list_backups(device: str | None = None) -> list[Path]:
    pattern = f"{device}_*.cfg" if device else "*.cfg"
    return sorted(BACKUPS_DIR.glob(pattern), reverse=True)


def rollback_device(device: str, backup_file: Path, inventory: Path) -> None:
    from netmiko import ConnectHandler

    hosts = load_inventory(inventory)
    if device not in hosts:
        raise SystemExit(f"{device} missing from inventory")
    config_lines = [
        line for line in backup_file.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith(("Building configuration", "Current configuration", "! Last"))
    ]
    params = netmiko_params(device, hosts[device])
    params.pop("name", None)
    with ConnectHandler(**params) as connection:
        if os.getenv("NET_SECRET"):
            connection.enable()
        output = connection.send_config_set(config_lines, read_timeout=180)
        print(output)
        print(connection.save_config())


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback device config from backup file")
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "inventories" / "lab_inventory.yml")
    parser.add_argument("--device")
    parser.add_argument("--backup-file", type=Path)
    parser.add_argument("--list", action="store_true", help="List backup files and exit")
    parser.add_argument("--apply", action="store_true", help="Actually push rollback config")
    args = parser.parse_args()

    if args.list:
        for path in list_backups(args.device):
            print(path)
        return 0
    if not args.device or not args.backup_file:
        raise SystemExit("--device and --backup-file are required unless --list is used")
    if not args.apply:
        print(f"Rollback dry-run for {args.device} using {args.backup_file}")
        print("Use --apply with CONFIRM_DEPLOY=true to push rollback.")
        return 0

    require_confirm_deploy("rollback device config")
    answer = input(f"Type ROLLBACK {args.device} to confirm: ").strip()
    if answer != f"ROLLBACK {args.device}":
        raise SystemExit("Rollback cancelled.")
    rollback_device(args.device, args.backup_file, args.inventory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
