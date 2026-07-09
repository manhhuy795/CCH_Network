"""Policy engine dùng chung cho controller, dashboard và test."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml


HQ_PROJECTS = {"project_a", "project_b", "project_c"}
BRANCH_GROUPS = {"telesale", "backoffice"}

GROUP_PATHS = {
    "project_a": ["project_a", "access_hq_a", "core_hq"],
    "project_b": ["project_b", "access_hq_b", "core_hq"],
    "project_c": ["project_c", "access_hq_c", "core_hq"],
    "telesale": ["telesale", "access_branch", "dist_branch"],
    "backoffice": ["backoffice", "access_branch", "dist_branch"],
}


class PolicyEngine:
    def __init__(self, path: Path):
        self.path = path
        self.data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.groups = self.data["host_groups"]
        self.services = self.data["services"]
        self.policies = self.data["policies"]
        self.networks = {
            name: ipaddress.ip_network(group["subnet"])
            for name, group in self.groups.items()
        }
        self.service_by_ip = {
            service["ip"]: name for name, service in self.services.items()
        }
        self.hosts = self._build_hosts()

    def _build_hosts(self) -> dict[str, dict[str, Any]]:
        hosts: dict[str, dict[str, Any]] = {}
        for group_name, group in self.groups.items():
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
        for name, service in self.services.items():
            hosts[name] = {
                "name": name,
                "label": service["label"],
                "ip": service["ip"],
                "kind": "service",
                "group": name,
                "group_label": service["label"],
                "vlan": 90 if name == "h90" else None,
                "site": "HQ" if name == "h90" else "Internet",
                "switch": service.get("switch", "internet"),
            }
        return hosts

    def endpoint_by_ip(self, ip: str) -> dict[str, Any] | None:
        return next((host for host in self.hosts.values() if host["ip"] == ip), None)

    def endpoint(self, name: str) -> dict[str, Any] | None:
        return self.hosts.get(name)

    def decide_ip(self, source_ip: str, destination_ip: str) -> dict[str, Any]:
        source = self.endpoint_by_ip(source_ip)
        destination = self.endpoint_by_ip(destination_ip)
        if not source or not destination:
            return {"action": "deny", "reason": "Mặc định từ chối: endpoint không thuộc policy."}
        return self.decide(source["name"], destination["name"])

    def decide(self, source_name: str, destination_name: str) -> dict[str, Any]:
        source = self.endpoint(source_name)
        destination = self.endpoint(destination_name)
        if not source or not destination:
            return {
                "action": "deny",
                "reason": "Không tìm thấy nguồn hoặc đích trong policy.",
                "path": [],
                "blocked_at": None,
            }

        if source["kind"] == "service" and destination["kind"] == "user":
            reverse = self.decide(destination_name, source_name)
            return {
                **reverse,
                "path": list(reversed(reverse["path"])),
                "reason": f"Luồng phản hồi hợp lệ. {reverse['reason']}",
            }
        if source["kind"] != "user":
            return self._result("deny", "Mặc định từ chối giữa các dịch vụ.", [], None)

        source_group = source["group"]
        if destination["kind"] == "service":
            return self._service_decision(source, destination)

        destination_group = destination["group"]
        if (
            self.policies["isolate_hq_projects"]
            and source_group in HQ_PROJECTS
            and destination_group in HQ_PROJECTS
            and source_group != destination_group
        ):
            path = GROUP_PATHS[source_group]
            reason = (
                f"User {source_name} thuộc VLAN {source['vlan']} bị chặn truy cập "
                f"user {destination_name} thuộc VLAN {destination['vlan']} "
                "theo chính sách cách ly project."
            )
            return self._result("deny", reason, path, "core_hq")

        if (
            self.policies["isolate_branch_vlan_50_60"]
            and {source_group, destination_group} == BRANCH_GROUPS
        ):
            return self._result(
                "deny",
                "Bị chặn bởi chính sách cách ly VLAN 50 và VLAN 60.",
                GROUP_PATHS[source_group],
                "dist_branch",
            )

        for rule in self.policies.get("intersite_allow", []):
            if {source_group, destination_group} == {
                rule["source_group"],
                rule["destination_group"],
            }:
                path = self._intersite_path(source_group, destination_group)
                return self._result(
                    "allow",
                    "Traffic liên site đi qua MPLS L3VPN Cloud. SDN Controller chỉ "
                    "điều khiển OVS ở hai đầu mạng, không điều khiển MPLS Cloud.",
                    path,
                    None,
                )

        if source_group == destination_group:
            path = [source_group, self.groups[source_group]["switch"], destination_group]
            return self._result("allow", "Cho phép nội bộ cùng nhóm.", path, None)
        return self._result("deny", "Mặc định từ chối theo SDN policy.", GROUP_PATHS[source_group], GROUP_PATHS[source_group][-1])

    @staticmethod
    def _result(action, reason, path, blocked_at):
        return {
            "action": action,
            "reason": reason,
            "path": list(path),
            "blocked_at": blocked_at,
            "expected_reachable": action == "allow",
        }

    def _service_decision(self, source, destination):
        source_path = GROUP_PATHS[source["group"]]
        service_name = destination["name"]
        if service_name == "h90" and self.policies["allow_voice"]:
            path = self._voice_path(source["group"])
            return self._result("allow", "Traffic Voice được cho phép và ưu tiên.", path, None)

        firewall = "fw_branch" if source["site"] == "Branch" else "fw_hq"
        path = [*source_path, firewall, "internet", service_name]
        labels = {
            "hzalo": ("allow_zalo", "Zalo"),
            "hcall": ("allow_call_app", "Call App"),
            "hinternet": ("allow_general_internet", "Internet chung"),
        }
        if service_name == "hsocial" and self.policies["block_social_media"]:
            return self._result(
                "deny",
                "Bị chặn bởi chính sách Internet Security: Block Social Media.",
                path[: path.index(firewall) + 1],
                firewall,
            )
        if service_name in labels:
            policy_key, label = labels[service_name]
            if self.policies[policy_key]:
                return self._result(
                    "allow",
                    f"{label} được cho phép. Traffic từ {source['site']} đi qua "
                    f"{'Firewall Branch' if source['site'] == 'Branch' else 'Firewall HQ'}.",
                    path,
                    None,
                )
        return self._result("deny", "Dịch vụ không nằm trong danh sách cho phép.", path[: path.index(firewall) + 1], firewall)

    def _voice_path(self, source_group):
        source_path = GROUP_PATHS[source_group]
        if source_group in BRANCH_GROUPS:
            return [
                *source_path,
                "ce_branch",
                "mpls_cloud",
                "ce_hq",
                "core_hq",
                "voice_mgmt",
                "h90",
            ]
        return [*source_path, "voice_mgmt", "h90"]

    @staticmethod
    def _intersite_path(source_group, destination_group):
        if source_group in BRANCH_GROUPS:
            return [
                *GROUP_PATHS[source_group],
                "ce_branch",
                "mpls_cloud",
                "ce_hq",
                "core_hq",
                GROUP_PATHS[destination_group][1],
                destination_group,
            ]
        return list(reversed(PolicyEngine._intersite_path(destination_group, source_group)))
