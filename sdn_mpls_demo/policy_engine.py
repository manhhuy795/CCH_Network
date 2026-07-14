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
BRANCH_GROUPS = {"telesale", "backoffice"}
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
        if source and destination and source["kind"] == "service" and destination["kind"] == "user":
            if icmp_type == ICMP_ECHO_REPLY:
                reverse = self.decide(destination_name, source_name)
                if reverse["action"] == "allow":
                    return {
                        **reverse,
                        "path": list(reversed(reverse["path"])),
                        "reason": f"Cho phep ICMP echo-reply cho phien do user noi bo khoi tao. {reverse['reason']}",
                    }
            return self._result(
                "deny",
                "Chan truy cap chu dong tu Internet/service vao user noi bo. Chi cho phep goi phan hoi hop le.",
                [source_name, "internet"],
                "internet",
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
                [source_name, "internet"],
                "internet",
            )
        if source["kind"] != "user":
            return self._result("deny", "Mac dinh tu choi giua cac dich vu.", [], None)

        source_group = source["group"]
        if self._is_it_support_flow(source_group, destination):
            return self._result(
                "allow",
                "IT Support co quyen remote/support co kiem soat theo policy.",
                self._it_support_path(source_group, destination),
                None,
            )

        if destination["kind"] == "service":
            return self._service_decision(source, destination)

        destination_group = destination["group"]
        if (
            self.policies["isolate_hq_projects"]
            and source_group in HQ_PROJECTS
            and destination_group in HQ_PROJECTS
            and source_group != destination_group
        ):
            reason = f"Bi chan boi chinh sach cach ly VLAN {source['vlan']} va VLAN {destination['vlan']}."
            return self._result("deny", reason, GROUP_PATHS[source_group], "core_hq")

        if (
            self.policies["isolate_branch_vlan_50_60"]
            and {source_group, destination_group} == BRANCH_GROUPS
        ):
            return self._result(
                "deny",
                "Bi chan boi chinh sach cach ly VLAN 50 va VLAN 60.",
                GROUP_PATHS[source_group],
                "dist_branch",
            )

        for rule in self.policies.get("intersite_allow", []):
            if {source_group, destination_group} == {rule["source_group"], rule["destination_group"]}:
                return self._result(
                    "allow",
                    "Traffic lien site di qua MPLS L3VPN Logic Cloud. SDN Controller chi dieu khien OVS o hai dau mang.",
                    self._intersite_path(source_group, destination_group),
                    None,
                )

        if source_group == destination_group:
            return self._result(
                "allow",
                "Cho phep noi bo cung nhom.",
                [source_group, self.groups[source_group]["switch"], destination_group],
                None,
            )
        return self._result("deny", "Mac dinh tu choi theo SDN Edge Policy.", GROUP_PATHS[source_group], GROUP_PATHS[source_group][-1])

    @staticmethod
    def _result(action: str, reason: str, path: list[str], blocked_at: str | None) -> dict[str, Any]:
        return {
            "action": action,
            "reason": reason,
            "path": list(path),
            "blocked_at": blocked_at,
            "expected_reachable": action == "allow",
        }

    def _service_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        source_group = source["group"]
        source_path = GROUP_PATHS[source_group]
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
            edge = "dist_branch" if source["site"] == "Branch" else "core_hq"
            return self._result(
                "deny",
                "Bi chan boi chinh sach SDN Edge: Social Media khong duoc phep doi voi user thuong.",
                source_path,
                edge,
            )

        firewall = "fw_branch" if source["site"] == "Branch" else "fw_hq"
        path = [*source_path, firewall, "internet", service_name]
        labels = {
            "hzalo": ("allow_zalo", "Zalo"),
            "hcall": ("allow_call_app", "Call App / CRM"),
            "hinternet": ("allow_general_internet", "General Internet Test Service"),
        }
        if service_name in labels:
            policy_key, label = labels[service_name]
            if self.policies[policy_key]:
                site_label = "Firewall Branch" if source["site"] == "Branch" else "Firewall HQ"
                return self._result(
                    "allow",
                    f"{label} duoc cho phep. Traffic Internet cua {source['site']} di qua {site_label}.",
                    path,
                    None,
                )
        return self._result("deny", "Dich vu khong nam trong danh sach cho phep.", [*source_path, firewall], firewall)

    def _voice_path(self, source_group: str) -> list[str]:
        source_path = GROUP_PATHS[source_group]
        if source_group in BRANCH_GROUPS:
            return [*source_path, "ce_branch", "mpls_cloud", "ce_hq", "core_hq", "voice_access", "h90"]
        return [*source_path, "voice_access", "h90"]

    def _is_it_support_flow(self, source_group: str, destination: dict[str, Any]) -> bool:
        return bool(
            self.policies.get("allow_it_support_controlled_access", False)
            and (
                source_group == IT_SUPPORT_GROUP
                or (destination["kind"] == "user" and destination["group"] == IT_SUPPORT_GROUP)
            )
        )

    def _it_support_path(self, source_group: str, destination: dict[str, Any]) -> list[str]:
        if source_group == IT_SUPPORT_GROUP:
            source_path = GROUP_PATHS[IT_SUPPORT_GROUP]
            if destination["kind"] == "service":
                if destination["name"] == "h90":
                    return [*source_path, "voice_access", "h90"]
                return [*source_path, "fw_hq", "internet", destination["name"]]
            destination_group = destination["group"]
            if destination_group in BRANCH_GROUPS:
                return [
                    *source_path,
                    "ce_hq",
                    "mpls_cloud",
                    "ce_branch",
                    "dist_branch",
                    GROUP_PATHS[destination_group][1],
                    destination_group,
                ]
            return [*source_path, GROUP_PATHS[destination_group][1], destination_group]

        return list(reversed(self._it_support_path(IT_SUPPORT_GROUP, {"kind": "user", "group": source_group})))

    @staticmethod
    def _intersite_path(source_group: str, destination_group: str) -> list[str]:
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
