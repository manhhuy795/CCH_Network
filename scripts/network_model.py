from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
NETWORK_MODEL_FILE = REPO_ROOT / "vars" / "network_model.yml"


def load_network_model(path: Path | None = None) -> dict[str, Any]:
    model_path = path or NETWORK_MODEL_FILE
    return yaml.safe_load(model_path.read_text(encoding="utf-8"))


def build_host_inventory(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    hosts: dict[str, dict[str, Any]] = {}
    for group_name, group in model["host_groups"].items():
        network = ipaddress.ip_network(group["subnet"])
        first_host = int(group.get("first_host", 11))
        for index in range(1, int(group["count"]) + 1):
            name = f"{group['prefix']}_{index:02d}"
            hosts[name] = {
                "name": name,
                "label": f"{group['label']} - User {index:02d}",
                "ip": str(network.network_address + first_host + index - 1),
                "kind": "user",
                "group": group_name,
                "group_label": group["label"],
                "vlan": int(group["vlan"]),
                "site": group["site"],
                "switch": group["switch"],
            }

    for name, service in model["services"].items():
        hosts[name] = {
            "name": name,
            "label": service["label"],
            "ip": service["ip"],
            "kind": "service",
            "group": name,
            "group_label": service["label"],
            "vlan": service.get("vlan"),
            "site": service.get("site", "Internet"),
            "switch": service.get("switch", "internet"),
        }
    return hosts


def controlled_switches(model: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        name
        for name, switch in model["switches"].items()
        if bool(switch.get("controlled"))
    )


def dpid_map(model: dict[str, Any]) -> dict[str, str]:
    return {
        name: switch["dpid"]
        for name, switch in model["switches"].items()
        if switch.get("dpid")
    }


def dpid_name_map(model: dict[str, Any]) -> dict[int, str]:
    return {
        int(switch["dpid"], 16): name
        for name, switch in model["switches"].items()
        if switch.get("dpid")
    }


def architecture_links(model: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [tuple(link) for link in model["links"]]


def user_count(model: dict[str, Any]) -> int:
    return sum(int(group["count"]) for group in model["host_groups"].values())
