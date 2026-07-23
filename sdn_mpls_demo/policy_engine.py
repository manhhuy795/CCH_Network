"""Policy engine dung chung cho controller, dashboard va test."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml

try:
    from scripts.network_model import (
        build_host_inventory,
        enforcement_switch_for_group,
        load_network_model,
    )
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.network_model import (
        build_host_inventory,
        enforcement_switch_for_group,
        load_network_model,
    )


HQ_PROJECTS = {"project_a", "project_b", "project_c"}
IT_SUPPORT_GROUP = "it_support"
ICMP_ECHO_REPLY = 0
ICMP_ECHO_REQUEST = 8

POLICY_FLOW_PROFILES: dict[str, dict[str, Any]] = {
    "hq_project_isolation": {"cookie": 0x1001, "priority": 400, "action": "DROP"},
    "telesale_backoffice_isolation": {"cookie": 0x1002, "priority": 400, "action": "DROP"},
    "voice": {"cookie": 0x1200, "priority": 425, "action": "ALLOW"},
    "it_support": {"cookie": 0x1301, "priority": 450, "action": "ALLOW"},
    "it_support_return": {"cookie": 0x1302, "priority": 450, "action": "ALLOW"},
    "it_inbound_block": {"cookie": 0x1303, "priority": 460, "action": "DROP"},
    "reactive_policy_drop": {"cookie": 0x1000, "priority": 300, "action": "DROP"},
    "transit_to_enforcement": {"cookie": 0x1100, "priority": 180, "action": "ALLOW"},
    "runtime": {"cookie": 0x0000, "priority": 0, "action": "PACKET_IN"},
}

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
        self.infrastructure_services = self.model.get("infrastructure_services", {})
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
            "infrastructure_services": self.infrastructure_services,
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
        return enforcement_switch_for_group(self.model, group_name)

    def isolation_flow_specs(self) -> list[dict[str, Any]]:
        """Build deterministic directional DROP specs for SDN edge enforcement."""
        pairs: list[tuple[str, str, str]] = []
        if self.policies.get("isolate_hq_projects", False):
            for left, right in (
                ("project_a", "project_b"),
                ("project_a", "project_c"),
                ("project_b", "project_c"),
            ):
                pairs.extend((
                    (left, right, "hq_project_isolation"),
                    (right, left, "hq_project_isolation"),
                ))
        if self.policies.get("isolate_telesale_backoffice", False):
            pairs.extend((
                ("telesale", "backoffice", "telesale_backoffice_isolation"),
                ("backoffice", "telesale", "telesale_backoffice_isolation"),
            ))

        specs: list[dict[str, Any]] = []
        for source_group, destination_group, policy_id in pairs:
            source_network = self.networks[source_group]
            destination_network = self.networks[destination_group]
            profile = POLICY_FLOW_PROFILES[policy_id]
            specs.append({
                "switch": self._enforcement_for_group(source_group),
                "source_group": source_group,
                "destination_group": destination_group,
                "source_network": str(source_network),
                "destination_network": str(destination_network),
                "match": {
                    "eth_type": "ipv4",
                    "ipv4_src": str(source_network),
                    "ipv4_dst": str(destination_network),
                },
                "action": profile["action"],
                "policy": policy_id,
                "cookie": int(profile["cookie"]),
                "priority": int(profile["priority"]),
            })
        return specs

    def isolation_flow_identities(self) -> tuple[tuple[Any, ...], ...]:
        """Stable identities used to prove reload planning cannot duplicate a flow."""
        return tuple(
            (
                spec["switch"],
                spec["cookie"],
                spec["priority"],
                spec["source_network"],
                spec["destination_network"],
                spec["action"],
            )
            for spec in self.isolation_flow_specs()
        )

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
        if source and destination and source["kind"] == "service" and destination["kind"] in {"user", "guest", "iot"}:
            firewall = self._site_node(str(destination["site"]), "firewall")
            return self._result(
                "deny",
                "Stateful nftables firewall chan ket noi moi tu Internet/service vao user noi bo.",
                [source_name, self._internet_node(), firewall],
                firewall,
            )
        return self.decide(source_name, destination_name)

    def decide(self, source_name: str, destination_name: str) -> dict[str, Any]:
        source = self.endpoint(source_name)
        destination = self.endpoint(destination_name)
        if not source or not destination:
            return self._result("deny", "Khong tim thay nguon hoac dich trong policy.", [], None)

        if source["kind"] == "service" and destination["kind"] in {"user", "guest", "iot"}:
            firewall = self._site_node(str(destination["site"]), "firewall")
            return self._result(
                "deny",
                "Stateful nftables firewall chan ket noi moi tu Internet/service vao user noi bo.",
                [source_name, self._internet_node(), firewall],
                firewall,
            )
        if source["kind"] == "service":
            return self._result(
                "deny",
                "Service khong duoc chu dong truy cap service khac trong Internet/Services zone.",
                [source_name, self._internet_node(), destination_name],
                self._internet_node(),
            )
        if destination["kind"] == "infrastructure_service":
            return self._infrastructure_service_decision(source, destination)
        if source["kind"] in {"guest", "iot"}:
            return self._enterprise_source_decision(source, destination)
        if source["kind"] == "infrastructure_service":
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
            self.policies["isolate_telesale_backoffice"]
            and {source_group, destination_group} == {"telesale", "backoffice"}
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
            firewall = self._site_node(str(source["site"]), "firewall")
            path = [*source_path, firewall]
            if source_group == IT_SUPPORT_GROUP:
                return self._result(
                    "deny",
                    "IT Support khong duoc bypass chinh sach Social Media tai nftables firewall HQ.",
                    path,
                    firewall,
                )
            return self._result(
                "deny",
                "Bi chan boi chinh sach Internet service tai stateful nftables firewall.",
                path,
                firewall,
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
                ["project_a", "project_b", "project_c", "telesale", "backoffice", "iot_ups"],
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
                firewall = self._site_node(str(source["site"]), "firewall")
                return self._result(
                    "deny",
                    "IT Support khong duoc bypass chinh sach Social Media tai nftables firewall HQ.",
                    [*self.group_paths[source_group], firewall],
                    firewall,
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

        if destination["kind"] == "infrastructure_service":
            if destination["name"] in {"hdhcp", "hdns", "hntp", "hmonitor"}:
                return self._result(
                    "allow",
                    "IT Support duoc quan tri infrastructure service theo management policy.",
                    self._infrastructure_service_path(source_group, destination["name"]),
                    None,
                )
            return self._result("deny", "IT Support khong co quyen toi infrastructure service nay.", self.group_paths[source_group], "core_hq")

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

    def _infrastructure_service_path(self, source_group: str, destination_name: str) -> list[str]:
        return [*self.group_paths[source_group], "infra_access", destination_name]

    def _infrastructure_service_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        allowed_sources = {
            "guest": {"hdhcp", "hdns", "hntp"},
            "iot_ups": {"hdhcp", "hdns", "hntp", "hmonitor"},
            "it_support": {"hdhcp", "hdns", "hntp", "hmonitor"},
        }
        source_group = str(source.get("group"))
        if destination["name"] in allowed_sources.get(source_group, set()):
            return self._result(
                "allow",
                "Infrastructure service duoc cho phep theo VLAN va least-privilege policy.",
                self._infrastructure_service_path(source_group, destination["name"]),
                None,
            )
        return self._result(
            "deny",
            "Infrastructure service chi cho phep DHCP/DNS/NTP va monitoring theo source group.",
            self.group_paths.get(source_group, []),
            "core_hq",
        )

    def _enterprise_source_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        source_group = str(source.get("group"))
        if source_group == "guest":
            if destination["name"] in {"hdhcp", "hdns", "hntp"}:
                return self._infrastructure_service_decision(source, destination)
            if destination["kind"] == "service" and destination["name"] == "hinternet":
                return self._service_decision(source, destination)
            return self._result(
                "deny",
                "Guest chi duoc dung DHCP/DNS/NTP va General Internet; mac dinh chan tai core_hq.",
                self.group_paths[source_group],
                "core_hq",
            )
        if source_group == "iot_ups":
            if destination["kind"] == "infrastructure_service":
                return self._infrastructure_service_decision(source, destination)
            return self._result(
                "deny",
                "IoT/UPS mac dinh khong duoc truy cap Corporate, Guest, Voice hoac Internet.",
                self.group_paths[source_group],
                "core_hq",
            )
        return self._result("deny", "Enterprise zone khong co policy cho phep.", self.group_paths.get(source_group, []), "core_hq")

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
