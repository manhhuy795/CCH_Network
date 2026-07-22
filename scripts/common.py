from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


REPO_ROOT = Path(__file__).resolve().parents[1]
VARS_DIR = REPO_ROOT / "vars"
TEMPLATES_DIR = REPO_ROOT / "templates"
GENERATED_DIR = REPO_ROOT / "generated_configs"
BACKUPS_DIR = REPO_ROOT / "backups"


def load_env() -> None:
    if load_dotenv:
        load_dotenv(REPO_ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def require_confirm_deploy(action: str) -> None:
    load_env()
    if not env_bool("CONFIRM_DEPLOY", False):
        raise SystemExit(
            f"Refusing to {action}: set CONFIRM_DEPLOY=true in environment or .env "
            "after lab validation and change approval."
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_vars() -> dict[str, Any]:
    config: dict[str, Any] = {}
    for filename in (
        "sites.yml",
        "vlans.yml",
        "routing.yml",
        "acl_policies.yml",
        "firewall_policies.yml",
        "interface_mapping.yml",
        "sdn.yml",
    ):
        path = VARS_DIR / filename
        if path.exists():
            config = deep_merge(config, load_yaml(path))
    return config


def all_devices(config: dict[str, Any]) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for site_id, site in config["sites"].items():
        for device in site.get("devices", []):
            device_copy = dict(device)
            device_copy["site"] = device_copy.get("site", site_id)
            devices.append(device_copy)
    return devices


def get_device(config: dict[str, Any], name: str) -> dict[str, Any]:
    for device in all_devices(config):
        if device["name"] == name:
            return device
    raise KeyError(f"Unknown device {name}")


def vlans_for_site(config: dict[str, Any], site: str) -> list[dict[str, Any]]:
    return [vlan for vlan in config["vlans"] if vlan["site"] == site]


def vlans_by_id(config: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(vlan["id"]): vlan for vlan in config["vlans"]}


def dotted_netmask(prefix: str) -> str:
    return str(ipaddress.ip_network(prefix, strict=False).netmask)


def wildcard_mask(prefix: str) -> str:
    return str(ipaddress.ip_network(prefix, strict=False).hostmask)


def ip_address(value: str) -> str:
    return str(ipaddress.ip_interface(value).ip)


def prefix_to_ios(prefix: str) -> str:
    network = ipaddress.ip_network(prefix, strict=False)
    return f"{network.network_address} {network.netmask}"


def prefix_to_acl(prefix: str) -> str:
    network = ipaddress.ip_network(prefix, strict=False)
    return f"{network.network_address} {network.hostmask}"


def acl_name_for_vlan(config: dict[str, Any], vlan_id: int) -> str | None:
    for policy in config.get("hq_project_isolation", []):
        if int(policy["source_vlan"]) == int(vlan_id):
            return policy["name"]
    management = config.get("management_policy", {})
    if int(management.get("source_vlan", -1)) == int(vlan_id):
        return management.get("name")
    for policy in config.get("branch_policies", []):
        if int(policy["source_vlan"]) == int(vlan_id):
            return policy["name"]
    return None


def jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["dotted_netmask"] = dotted_netmask
    env.filters["wildcard_mask"] = wildcard_mask
    env.filters["ip_address"] = ip_address
    env.filters["prefix_to_ios"] = prefix_to_ios
    env.filters["prefix_to_acl"] = prefix_to_acl
    env.globals["acl_name_for_vlan"] = acl_name_for_vlan
    return env


def render_device_config(config: dict[str, Any], device: dict[str, Any]) -> str:
    template = jinja_env().get_template(device["template"])
    return template.render(
        config=config,
        device=device,
        vlans_by_id=vlans_by_id(config),
        site_vlans=vlans_for_site(config, device["site"]),
        interfaces=config.get("interfaces", {}).get(device["name"], {}),
        routes=(
            config.get("routes", {}).get(device["name"])
            or config.get("routes", {}).get(device.get("model_node", ""), {})
        ),
        firewall_site=config.get("firewall_policy", {}).get("sites", {}).get(device["site"], {}),
    )
