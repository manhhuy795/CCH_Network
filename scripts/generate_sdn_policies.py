from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import GENERATED_DIR, jinja_env, load_env, load_vars, require_confirm_deploy


def validate_sdn(config: dict) -> list[str]:
    errors: list[str] = []
    sdn = config.get("sdn", {})
    if not sdn.get("enabled", False):
        return errors

    vlan_ids = {int(vlan["id"]) for vlan in config.get("vlans", [])}
    fabric_devices = {device for device in sdn.get("fabric_scope", [])}
    known_devices = {
        device["name"]
        for site in config.get("sites", {}).values()
        for device in site.get("devices", [])
    }
    missing_devices = fabric_devices - known_devices
    if missing_devices:
        errors.append(f"SDN fabric_scope references unknown devices: {sorted(missing_devices)}")

    for intent in sdn.get("intents", []):
        for key in ("source_vlan",):
            if key in intent and int(intent[key]) not in vlan_ids:
                errors.append(f"SDN intent {intent['name']} references missing {key} {intent[key]}")
        for key in ("source_vlans", "deny_destination_vlans", "allow_destination_vlans"):
            for vlan_id in intent.get(key, []):
                if int(vlan_id) not in vlan_ids:
                    errors.append(f"SDN intent {intent['name']} references missing {key} VLAN {vlan_id}")

    return errors


def render_sdn_policy(output_dir: Path = GENERATED_DIR) -> Path:
    config = load_vars()
    errors = validate_sdn(config)
    if errors:
        raise SystemExit("SDN validation failed:\n" + "\n".join(f"- {error}" for error in errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    template = jinja_env().get_template("sdn/intent_policy.json.j2")
    rendered = template.render(config=config)
    parsed = json.loads(rendered)
    output_path = output_dir / "sdn_intents.json"
    output_path.write_text(json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def apply_sdn_policy(policy_file: Path) -> None:
    import requests

    load_env()
    require_confirm_deploy("apply SDN intent policy")
    config = load_vars()
    controller = config["sdn"]["controller"]
    base_url = os.getenv(controller["url_env"], "").rstrip("/")
    if not base_url:
        raise SystemExit(f"{controller['url_env']} must be set for SDN apply")

    username = os.getenv(controller["username_env"], "")
    password = os.getenv(controller["password_env"], "")
    auth = (username, password) if username or password else None
    url = base_url + controller.get("api_path", "/api/v1/network-intents")
    payload = json.loads(policy_file.read_text(encoding="utf-8"))
    response = requests.post(url, json=payload, auth=auth, timeout=30)
    response.raise_for_status()
    print(f"SDN controller accepted intent policy: HTTP {response.status_code}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render or apply optional SDN intent policy")
    parser.add_argument("--output-dir", type=Path, default=GENERATED_DIR)
    parser.add_argument("--apply", action="store_true", help="POST intents to SDN controller")
    args = parser.parse_args()

    output_path = render_sdn_policy(args.output_dir)
    if not args.apply:
        print(f"Rendered SDN intent policy: {output_path}")
        print("Dry-run only. Use --apply with CONFIRM_DEPLOY=true and SDN_CONTROLLER_URL for live controller.")
        return 0

    apply_sdn_policy(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
