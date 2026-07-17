"""Policy engine dung chung cho controller, dashboard va test."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml

try:
    from scripts.network_model import build_host_inventory, load_network_model
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.network_model import build_host_inventory, load_network_model


HQ_PROJECTS = {"project_a", "project_b", "project_c"}
IT_SUPPORT_GROUP = "it_support"
ICMP_ECHO_REPLY = 0
ICMP_ECHO_REQUEST = 8

NETWORK_MODEL = load_network_model()
GROUP_PATHS = {
    group_name: list(path)
    for group_name, path in NETWORK_MODEL["group_paths"].items()
}


class PolicyEngine:
    def __init__(self, path: Path):
        self.path = path
        self.policy_data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.model = load_network_model()
        self.groups = self.model["host_groups"]
        self.services = self.model["services"]
        self.switches = self.model["switches"]
        self.infrastructure = self.model["infrastructure"]
        self.group_paths = {
            group_name: list(group_path)
            for group_name, group_path in self.model["group_paths"].items()
        }
        self.policies = self.policy_data["policies"]
        self.runtime = self.policy_data.get("runtime", {})
        self.data = {
            "metadata": {
                **self.model.get("metadata", {}),
                **self.policy_data.get("metadata", {}),
            },
            "host_groups": self.groups,
            "services": self.services,
            "switches": self.switches,
            "policies": self.policies,
            "runtime": self.runtime,
        }
        self.networks = {
            name: ipaddress.ip_network(group["subnet"])
            for name, group in self.groups.items()
        }
        self.service_by_ip = {
            service["ip"]: name for name, service in self.services.items()
        }
        self.hosts = build_host_inventory(self.model)

    def endpoint_by_ip(self, ip: str) -> dict[str, Any] | None:
        return next((host for host in self.hosts.values() if host["ip"] == ip), None)

    def endpoint(self, name: str) -> dict[str, Any] | None:
        return self.hosts.get(name)

    def _site_node(self, site: str, node_type: str) -> str:
        matches = [
            name
            for name, node in self.infrastructure.items()
            if node.get("site") == site and node.get("type") == node_type
        ]
        if len(matches) != 1:
            raise ValueError(f"Site {site} must have exactly one {node_type}, found {matches}")
        return matches[0]

    def _wan_node(self) -> str:
        matches = [name for name, node in self.infrastructure.items() if node.get("type") == "wan"]
        if len(matches) != 1:
            raise ValueError(f"Network model must have exactly one WAN node, found {matches}")
        return matches[0]

    def _internet_node(self) -> str:
        return str(self.model["service_addressing"]["gateway_node"])

    def _enforcement_for_group(self, group_name: str) -> str:
        return self.group_paths[group_name][-1]

    def _path_between_groups(self, source_group: str, destination_group: str) -> list[str]:
        source_path = self.group_paths[source_group]
        destination_path = self.group_paths[destination_group]
        source_site = self.groups[source_group]["site"]
        destination_site = self.groups[destination_group]["site"]
        destination_reverse = list(reversed(destination_path))
        if source_site == destination_site:
            return [*source_path, *destination_reverse[1:]]
        return [
            *source_path,
            self._site_node(source_site, "router"),
            self._wan_node(),
            self._site_node(destination_site, "router"),
            *destination_reverse,
        ]

    def decide_ip(self, source_ip: str, destination_ip: str, icmp_type: int | None = None) -> dict[str, Any]:
        source = self.endpoint_by_ip(source_ip)
        destination = self.endpoint_by_ip(destination_ip)
        if not source or not destination:
            return {"action": "deny", "reason": "Mac dinh tu choi: endpoint khong thuoc policy.", "path": [], "blocked_at": None}
        if icmp_type is not None:
            return self.decide_packet(source["name"], destination["name"], icmp_type=icmp_type)
        return self.decide(source["name"], destination["name"])

    def decide_packet(self, source_name: str, destination_name: str, icmp_type: int | None = None) -> dict[str, Any]:
        source = self.endpoint(source_name)
        destination = self.endpoint(destination_name)
        if source and destination and icmp_type == ICMP_ECHO_REPLY:
            reverse = self.decide(destination_name, source_name)
            if reverse["action"] == "allow":
                return {
                    **reverse,
                    "path": list(reversed(reverse["path"])),
                    "reason": f"Cho phep ICMP echo-reply cho phien do endpoint noi bo khoi tao. {reverse['reason']}",
                }
        if source and destination and source["kind"] == "service" and destination["kind"] == "user":
            return self._result(
                "deny",
                "Chan truy cap chu dong tu Internet/service vao user noi bo. Chi cho phep goi phan hoi hop le.",
                [source_name, self._internet_node()],
                self._internet_node(),
            )
        return self.decide(source_name, destination_name)

    def decide(self, source_name: str, destination_name: str) -> dict[str, Any]:
        source = self.endpoint(source_name)
        destination = self.endpoint(destination_name)
        if not source or not destination:
            return self._result("deny", "Khong tim thay nguon hoac dich trong policy.", [], None)

        if source["kind"] == "service" and destination["kind"] == "user":
            return self._result(
                "deny",
                "Chan truy cap chu dong tu Internet/service vao user noi bo.",
                [source_name, self._internet_node()],
                self._internet_node(),
            )
        if source["kind"] != "user":
            return self._result("deny", "Mac dinh tu choi giua cac dich vu.", [], None)

        source_group = source["group"]
        if (
            destination["kind"] == "service"
            and destination["name"] == "hsocial"
            and self.policies["block_social_media"]
        ):
            return self._service_decision(source, destination)

        if source_group == IT_SUPPORT_GROUP:
            return self._it_support_decision(source, destination)

        if destination["kind"] == "service":
            return self._service_decision(source, destination)

        destination_group = destination["group"]
        if source_group != IT_SUPPORT_GROUP and destination_group == IT_SUPPORT_GROUP:
            return self._result(
                "deny",
                "User thuong khong duoc chu dong truy cap VLAN IT Support.",
                self._path_to_core_hq(source_group),
                "core_hq",
            )

        if (
            self.policies["isolate_hq_projects"]
            and source_group in HQ_PROJECTS
            and destination_group in HQ_PROJECTS
            and source_group != destination_group
        ):
            reason = f"Bi chan boi chinh sach cach ly VLAN {source['vlan']} va VLAN {destination['vlan']}."
            return self._result("deny", reason, self.group_paths[source_group], "core_hq")

        if (
            self.policies["isolate_branch_vlan_50_60"]
            and {int(source["vlan"]), int(destination["vlan"])} == {50, 60}
        ):
            return self._result(
                "deny",
                "Bi chan boi chinh sach cach ly VLAN 50 va VLAN 60.",
                self.group_paths[source_group],
                self._enforcement_for_group(source_group),
            )

        for rule in self.policies.get("intersite_allow", []):
            if {source_group, destination_group} == {rule["source_group"], rule["destination_group"]}:
                return self._result(
                    "allow",
                    "Traffic lien site di qua MPLS L3VPN Logic Cloud. SDN Controller chi dieu khien OVS o hai dau mang.",
                    self._path_between_groups(source_group, destination_group),
                    None,
                )

        if source_group == destination_group:
            return self._result(
                "allow",
                "Cho phep noi bo cung nhom.",
                [source_group, self.groups[source_group]["switch"], destination_group],
                None,
            )
        return self._result(
            "deny",
            "Mac dinh tu choi theo SDN Edge Policy.",
            self.group_paths[source_group],
            self._enforcement_for_group(source_group),
        )

    @staticmethod
    def _result(action: str, reason: str, path: list[str], blocked_at: str | None) -> dict[str, Any]:
        return {
            "action": action,
            "reason": reason,
            "path": list(path),
            "blocked_at": blocked_at,
            "enforcement_point": blocked_at,
            "expected_reachable": action == "allow",
        }

    def _service_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        source_group = source["group"]
        source_path = self.group_paths[source_group]
        service_name = destination["name"]
        if service_name == "h90" and self.policies["allow_voice"]:
            result = self._result(
                "allow",
                "Voice duoc nhan dien va ap dung flow policy uu tien.",
                self._voice_path(source_group),
                None,
            )
            result["voice_flow_priority"] = bool(self.policies.get("voice_flow_priority", False))
            return result

        if service_name == "hsocial" and self.policies["block_social_media"]:
            edge = self._enforcement_for_group(source_group)
            if source_group == IT_SUPPORT_GROUP:
                return self._result(
                    "deny",
                    "IT Support khong duoc bypass chinh sach chan Social Media.",
                    source_path,
                    "core_hq",
                )
            return self._result(
                "deny",
                "Bi chan boi chinh sach SDN Edge: Social Media khong duoc phep doi voi user thuong.",
                source_path,
                edge,
            )

        firewall = self._site_node(str(source["site"]), "firewall")
        path = [*source_path, firewall, self._internet_node(), service_name]
        labels = {
            "hzalo": ("allow_zalo", "Zalo"),
            "hcall": ("allow_call_app", "Call App / CRM"),
            "hinternet": ("allow_general_internet", "General Internet Test Service"),
        }
        if service_name in labels:
            policy_key, label = labels[service_name]
            if self.policies[policy_key]:
                site_label = self.infrastructure[firewall]["label"]
                return self._result(
                    "allow",
                    f"{label} duoc cho phep. Traffic Internet cua {source['site']} di qua {site_label}.",
                    path,
                    None,
                )
        return self._result("deny", "Dich vu khong nam trong danh sach cho phep.", [*source_path, firewall], firewall)

    def _voice_path(self, source_group: str) -> list[str]:
        source_path = self.group_paths[source_group]
        source_site = self.groups[source_group]["site"]
        voice = self.services["h90"]
        voice_site = voice["site"]
        voice_tail = [voice["switch"], "h90"]
        if source_site == voice_site:
            return [*source_path, *voice_tail]
        return [
            *source_path,
            self._site_node(source_site, "router"),
            self._wan_node(),
            self._site_node(voice_site, "router"),
            voice["gateway_node"],
            *voice_tail,
        ]

    def _it_support_policy(self) -> dict[str, Any]:
        configured = self.policies.get("it_support_controlled_access") or {}
        fallback_services = self.policies.get("it_support_allowed_services", ["h90", "hzalo", "hcall"])
        return {
            "enabled": configured.get("enabled", self.policies.get("allow_it_support_controlled_access", False)),
            "source_group": configured.get("source_group", IT_SUPPORT_GROUP),
            "allow_icmp_to_managed_users": configured.get("allow_icmp_to_managed_users", True),
            "managed_user_groups": configured.get(
                "managed_user_groups",
                ["project_a", "project_b", "project_c", "telesale", "backoffice"],
            ),
            "allowed_services": configured.get("allowed_services", fallback_services),
            "denied_services": configured.get("denied_services", ["hsocial"]),
            "management_tcp_ports": configured.get("management_tcp_ports", [22, 443, 3389, 5985, 5986]),
        }

    def _it_support_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        policy = self._it_support_policy()
        source_group = source["group"]
        if not policy["enabled"] or source_group != policy["source_group"]:
            return self._result("deny", "IT Support controlled access bi tat hoac sai source group.", self.group_paths[source_group], "core_hq")

        if destination["kind"] == "service":
            service_name = destination["name"]
            denied_services = set(policy["denied_services"])
            allowed_services = set(policy["allowed_services"])
            if service_name in denied_services or (service_name == "hsocial" and self.policies["block_social_media"]):
                return self._result(
                    "deny",
                    "IT Support khong duoc bypass chinh sach chan Social Media.",
                    self.group_paths[source_group],
                    "core_hq",
                )
            if service_name in allowed_services:
                return self._result(
                    "allow",
                    "IT Support duoc kiem tra dich vu quan tri duoc khai bao theo policy.",
                    self._it_support_path(source_group, destination),
                    None,
                )
            return self._result(
                "deny",
                "IT Support least privilege: dich vu khong nam trong danh sach quan tri duoc phep.",
                self.group_paths[source_group],
                "core_hq",
            )

        destination_group = destination["group"]
        if policy["allow_icmp_to_managed_users"] and destination_group in set(policy["managed_user_groups"]):
            return self._result(
                "allow",
                "IT Support duoc chu dong remote/support user trong nhom managed.",
                self._it_support_path(source_group, destination),
                None,
            )
        return self._result(
            "deny",
            "IT Support least privilege: nhom dich khong nam trong managed_user_groups.",
            self.group_paths[source_group],
            "core_hq",
        )

    def _it_support_path(self, source_group: str, destination: dict[str, Any]) -> list[str]:
        if source_group == IT_SUPPORT_GROUP:
            source_path = self.group_paths[IT_SUPPORT_GROUP]
            if destination["kind"] == "service":
                if destination["name"] == "h90":
                    return [*source_path, "voice_access", "h90"]
                firewall = self._site_node(self.groups[source_group]["site"], "firewall")
                return [*source_path, firewall, self._internet_node(), destination["name"]]
            destination_group = destination["group"]
            return self._path_between_groups(source_group, destination_group)
        return self.group_paths.get(source_group, [])

    def _path_to_core_hq(self, source_group: str) -> list[str]:
        source_path = self.group_paths[source_group]
        source_site = self.groups[source_group]["site"]
        if source_site == "hq":
            return source_path
        return [
            *source_path,
            self._site_node(source_site, "router"),
            self._wan_node(),
            self._site_node("hq", "router"),
            "core_hq",
        ]
