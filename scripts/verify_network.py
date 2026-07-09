from __future__ import annotations

import argparse
import re
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
    "show running-config section access-list",
]


def verify_generated(config_dir: Path = GENERATED_DIR) -> list[str]:
    errors = validate_all(load_vars())
    hq_core = config_dir / "hq-core-l3.cfg"
    hq_ce = config_dir / "hq-ce-router.cfg"
    br_ce = config_dir / "br-ce-router.cfg"

    if hq_core.exists():
        text = hq_core.read_text(encoding="utf-8")
        for acl_name, denied in {
            "ACL_VLAN20_IN": ("172.16.30.0 0.0.0.255", "172.16.40.0 0.0.0.255"),
            "ACL_VLAN30_IN": ("172.16.20.0 0.0.0.255", "172.16.40.0 0.0.0.255"),
            "ACL_VLAN40_IN": ("172.16.20.0 0.0.0.255", "172.16.30.0 0.0.0.255"),
        }.items():
            if acl_name not in text:
                errors.append(f"{acl_name} missing from HQ core config")
            for prefix in denied:
                if prefix not in text:
                    errors.append(f"{acl_name} missing deny reference to {prefix}")
        if "ip route 0.0.0.0 0.0.0.0 10.10.254.2" not in text:
            errors.append("HQ core default route to firewall missing")
    else:
        errors.append(f"Missing {hq_core}; run generate_configs.py first")

    for ce_file, forbidden_next_hops in (
        (hq_ce, ["10.20.255.2", "198.51.100.2"]),
        (br_ce, ["10.10.255.2", "203.0.113.2"]),
    ):
        if ce_file.exists():
            text = ce_file.read_text(encoding="utf-8")
            for next_hop in forbidden_next_hops:
                if re.search(rf"^ip route .+ {re.escape(next_hop)}$", text, re.MULTILINE):
                    errors.append(f"{ce_file.name} has forbidden direct route to remote CE {next_hop}")
        else:
            errors.append(f"Missing {ce_file}; run generate_configs.py first")
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
