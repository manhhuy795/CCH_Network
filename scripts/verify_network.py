from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.backup_configs import load_inventory, netmiko_params
from scripts.common import GENERATED_DIR, REPO_ROOT, load_vars, require_confirm_deploy
from scripts.validate_vars import validate_all


SHOW_COMMANDS = [
    "show vlan brief",
    "show ip interface brief",
    "show interfaces trunk",
    "show ip route",
    "show access-lists",
]


def _read_required(config_dir: Path, name: str, errors: list[str]) -> str:
    path = config_dir / name
    if not path.exists():
        errors.append(f"Missing {path}; run generate_configs.py first")
        return ""
    return path.read_text(encoding="utf-8")


def verify_generated(config_dir: Path = GENERATED_DIR) -> list[str]:
    errors = validate_all(load_vars())
    hq_core = _read_required(config_dir, "hq-core-dist.cfg", errors)
    br_core = _read_required(config_dir, "br-core-dist.cfg", errors)

    if hq_core:
        for expected in (
            "interface Vlan93",
            "ip address 10.10.93.1 255.255.255.0",
            "ip helper-address 10.10.100.10",
            "ip route 0.0.0.0 0.0.0.0 10.10.254.2",
            "ACL_VLAN93_IN",
            "ACL_GUEST_IN",
            "ACL_IOT_HQ_IN",
            "host 10.10.100.12",
            "host 10.10.100.13",
        ):
            if expected not in hq_core:
                errors.append(f"HQ Core-Dist missing: {expected}")
        if "Port-channel" in hq_core:
            errors.append("HQ candidate config must not invent Port-channel before physical HA technology is confirmed")
        if "deny ip 10.10.101.0 0.0.0.255 10.10.0.0 0.0.255.255 log" not in hq_core:
            errors.append("Project 1 ACL must deny other internal HQ destinations after explicit service allows")

    if br_core:
        if "interface Vlan93" in br_core:
            errors.append("Branch Core-Dist must not create interface Vlan93")
        for expected in (
            "interface Vlan50",
            "ip address 10.20.50.1 255.255.255.0",
            "ip helper-address 10.10.100.10",
            "ip route 0.0.0.0 0.0.0.0 10.20.254.2",
        ):
            if expected not in br_core:
                errors.append(f"Branch Core-Dist missing: {expected}")
        if "Port-channel" in br_core:
            errors.append("Branch candidate config must not invent Port-channel before physical HA technology is confirmed")

    for name in ("hq-ce1.cfg", "hq-ce2.cfg", "br-ce1.cfg", "br-ce2.cfg"):
        text = _read_required(config_dir, name, errors)
        if not text:
            continue
        if "vlan 93" not in text or "switchport access vlan 93" not in text:
            errors.append(f"{name} must expose VLAN 93 on the customer attachment")
        for forbidden in ("xconnect ", "mpls ip", "pseudowire-class"):
            if forbidden in text.lower():
                errors.append(f"{name} invents provider MPLS syntax: {forbidden.strip()}")

    for name in ("hq-firewall-ha.policy.txt", "br-firewall-ha.policy.txt"):
        text = _read_required(config_dir, name, errors)
        if text and "tunnel:" not in text:
            errors.append(f"{name} must expose the logical firewall-to-firewall tunnel attachment")

    return errors


def run_live_verify(inventory: Path, limit: list[str] | None) -> None:
    from netmiko import ConnectHandler

    require_confirm_deploy("connect to devices for live verify")
    hosts = load_inventory(inventory)
    for name, host in hosts.items():
        if limit and name not in limit:
            continue
        params = netmiko_params(name, host)
        params.pop("name", None)
        with ConnectHandler(**params) as connection:
            print(f"\n## {name}")
            for command in SHOW_COMMANDS:
                print(f"\n# {command}")
                print(connection.send_command(command, read_timeout=60))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify generated or live network state")
    parser.add_argument("--config-dir", type=Path, default=GENERATED_DIR)
    parser.add_argument("--live", action="store_true", help="Run show commands on devices")
    parser.add_argument("--inventory", type=Path, default=REPO_ROOT / "inventories" / "lab_inventory.yml")
    parser.add_argument("--limit", nargs="*")
    args = parser.parse_args()

    if args.live:
        run_live_verify(args.inventory, args.limit)
        return 0

    errors = verify_generated(args.config_dir)
    if errors:
        print("Offline verify failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Offline verify passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
