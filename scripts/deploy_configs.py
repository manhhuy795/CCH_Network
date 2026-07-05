from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.backup_configs import load_inventory, netmiko_params
from scripts.common import GENERATED_DIR, REPO_ROOT, all_devices, load_vars, require_confirm_deploy
from scripts.generate_configs import generate_configs


BASIC_VERIFY_COMMANDS = {
    "cisco_ios": ["show ip interface brief", "show ip route"],
}


def ordered_devices(config: dict[str, Any]) -> list[dict[str, Any]]:
    order = {role: index for index, role in enumerate(config.get("deployment_order", []))}
    return sorted(all_devices(config), key=lambda device: order.get(device["role"], 999))


def config_path_for(device: dict[str, Any], config_dir: Path = GENERATED_DIR) -> Path:
    suffix = ".policy.txt" if device["role"] == "firewall" else ".cfg"
    return config_dir / f"{device['name']}{suffix}"


def deploy_device(device: dict[str, Any], host: dict[str, Any], config_path: Path) -> None:
    if device["role"] == "firewall":
        print(f"Skipping vendor-neutral firewall deploy for {device['name']}; review policy file manually.")
        return

    from netmiko import ConnectHandler

    params = netmiko_params(device["name"], host)
    params.pop("name", None)
    with ConnectHandler(**params) as connection:
        if os.getenv("NET_SECRET"):
            connection.enable()
        print(f"Deploying {config_path.name} to {device['name']}")
        output = connection.send_config_from_file(str(config_path), read_timeout=120)
        print(output)
        for command in BASIC_VERIFY_COMMANDS.get(device["platform"], []):
            print(f"\n# {device['name']} :: {command}")
            print(connection.send_command(command, read_timeout=60))


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy generated configs with dry-run default")
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "inventories" / "lab_inventory.yml")
    parser.add_argument("--config-dir", type=Path, default=GENERATED_DIR)
    parser.add_argument("--limit", nargs="*", help="Device names to deploy")
    parser.add_argument("--apply", action="store_true", help="Actually connect and push configs")
    parser.add_argument("--generate", action="store_true", help="Render configs before deploying")
    args = parser.parse_args()

    config = load_vars()
    if args.generate:
        generate_configs(args.config_dir)

    hosts = load_inventory(args.inventory)
    devices = [
        device for device in ordered_devices(config) if not args.limit or device["name"] in args.limit
    ]

    if not args.apply:
        print("Deploy dry-run. No device connection will be attempted.")
        for device in devices:
            path = config_path_for(device, args.config_dir)
            print(f"- {device['name']} role={device['role']} config={path} exists={path.exists()}")
        print("Use --apply only after backup, lab test, change approval, and CONFIRM_DEPLOY=true.")
        return 0

    require_confirm_deploy("deploy generated configs")
    for device in devices:
        if device["name"] not in hosts:
            raise SystemExit(f"{device['name']} missing from inventory")
        path = config_path_for(device, args.config_dir)
        if not path.exists():
            raise SystemExit(f"Missing generated config {path}. Run generate first.")
        deploy_device(device, hosts[device["name"]], path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
