"""Policy engine shared by OS-Ken, FastAPI and the enterprise v7 tests."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Any

import yaml

try:
    from scripts.network_model import build_host_inventory, enforcement_switch_for_group, load_network_model
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.network_model import build_host_inventory, enforcement_switch_for_group, load_network_model


PROJECT_GROUPS = {"project_1", "project_2", "project_3", "project_4"}
HQ_PROJECTS = PROJECT_GROUPS  # compatibility alias for controller/tests
IT_SUPPORT_GROUP = "it_support"
ICMP_ECHO_REPLY = 0
ICMP_ECHO_REQUEST = 8

POLICY_FLOW_PROFILES: dict[str, dict[str, Any]] = {
    "hq_project_isolation": {"cookie": 0x1001, "priority": 400, "action": "DROP"},
    "voice": {"cookie": 0x1200, "priority": 425, "action": "ALLOW"},
    "it_support": {"cookie": 0x1301, "priority": 450, "action": "ALLOW"},
    "it_support_return": {"cookie": 0x1302, "priority": 450, "action": "ALLOW"},
    "it_inbound_block": {"cookie": 0x1303, "priority": 460, "action": "DROP"},
    "it_social_block": {"cookie": 0x1304, "priority": 480, "action": "DROP"},
    "reactive_policy_drop": {"cookie": 0x1000, "priority": 300, "action": "DROP"},
    "transit_to_enforcement": {"cookie": 0x1100, "priority": 180, "action": "ALLOW"},
    "runtime": {"cookie": 0x0000, "priority": 0, "action": "PACKET_IN"},
}

NETWORK_MODEL = load_network_model()
GROUP_PATHS = {name: list(path) for name, path in NETWORK_MODEL["group_paths"].items()}


class PolicyEngine:
    def __init__(self, path: Path):
        self.path = path
        self.policy_data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self.model = load_network_model()
        self.groups = self.model["host_groups"]
        self.services = self.model["services"]
        self.infrastructure_services = self.model.get("infrastructure_services", {})
        self.switches = self.model["switches"]
        self.infrastructure = self.model["infrastructure"]
        self.group_paths = {name: list(value) for name, value in self.model["group_paths"].items()}
        self.site_group_paths = {
            name: {site: list(path_value) for site, path_value in paths.items()}
            for name, paths in self.model.get("site_group_paths", {}).items()
        }
        self.policies = self.policy_data.get("policies", {})
        self.runtime = self.policy_data.get("runtime", {})
        self.data = {
            "metadata": {**self.model.get("metadata", {}), **self.policy_data.get("metadata", {})},
            "host_groups": self.groups,
            "services": self.services,
            "infrastructure_services": self.infrastructure_services,
            "switches": self.switches,
            "policies": self.policies,
            "runtime": self.runtime,
        }
        self.networks = {name: ipaddress.ip_network(group["subnet"]) for name, group in self.groups.items()}
        self.service_by_ip = {str(service["ip"]): name for name, service in self.services.items()}
        self.hosts = build_host_inventory(self.model)

    def endpoint(self, name: str) -> dict[str, Any] | None:
        return self.hosts.get(name)

    def endpoint_by_ip(self, ip: str) -> dict[str, Any] | None:
        return next((host for host in self.hosts.values() if host["ip"] == ip), None)

    def _path_for_endpoint(self, endpoint: dict[str, Any]) -> list[str]:
        group_name = str(endpoint["group"])
        site = str(endpoint.get("site") or self.groups[group_name].get("site"))
        site_path = self.site_group_paths.get(group_name, {}).get(site)
        if site_path:
            return list(site_path)
        return list(self.group_paths.get(group_name, []))

    def _gateway_site(self, endpoint: dict[str, Any]) -> str:
        group = self.groups.get(str(endpoint.get("group")), {})
        return str(group.get("gateway_site") or endpoint.get("site") or group.get("site"))

    def _enforcement_for_group(self, group_name: str) -> str:
        return enforcement_switch_for_group(self.model, group_name)

    def _site_gateway(self, site: str) -> str:
        if site == "hq":
            return "core_hq"
        if site == "branch":
            return "dist_branch"
        raise ValueError(f"Unsupported physical site {site}")

    def _site_firewall(self, site: str) -> str:
        return "fw_hq" if site == "hq" else "fw_telesale"

    def _internet_node(self) -> str:
        return str(self.model["service_addressing"]["gateway_node"])

    def isolation_flow_specs(self) -> list[dict[str, Any]]:
        if not self.policies.get("isolate_hq_projects", False):
            return []
        specs: list[dict[str, Any]] = []
        project_names = sorted(PROJECT_GROUPS)
        profile = POLICY_FLOW_PROFILES["hq_project_isolation"]
        for source_group in project_names:
            for destination_group in project_names:
                if source_group == destination_group:
                    continue
                source_network = self.networks[source_group]
                destination_network = self.networks[destination_group]
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
                    "policy": "hq_project_isolation",
                    "cookie": int(profile["cookie"]),
                    "priority": int(profile["priority"]),
                })
        return specs

    def isolation_flow_identities(self) -> tuple[tuple[Any, ...], ...]:
        return tuple(
            (
                item["switch"], item["cookie"], item["priority"],
                item["source_network"], item["destination_network"], item["action"],
            )
            for item in self.isolation_flow_specs()
        )

    def _result(self, action: str, reason: str, path: list[str], blocked_at: str | None) -> dict[str, Any]:
        return {
            "action": action,
            "reason": reason,
            "path": list(path),
            "blocked_at": blocked_at,
            "enforcement_point": blocked_at,
            "expected_reachable": action == "allow",
        }

    def _project2_l2_path(self, source: dict[str, Any], destination: dict[str, Any]) -> list[str]:
        path = [
            "project_2", "access_branch", "dist_branch", "ce_branch1",
            "l2vpn_primary", "ce_hq1", "core_hq", "access_floor1", "project_2",
        ]
        if source.get("site") == "hq":
            path.reverse()
        return path

    def _routed_between_sites(self, source_path: list[str], source_site: str, destination_path: list[str], destination_site: str) -> list[str]:
        if source_site == destination_site:
            return [*source_path, *list(reversed(destination_path))[1:]]
        source_gateway = self._site_gateway(source_site)
        destination_gateway = self._site_gateway(destination_site)
        left = list(source_path)
        if not left or left[-1] != source_gateway:
            left.append(source_gateway)
        right = list(reversed(destination_path))
        if right and right[0] == destination_gateway:
            right = right[1:]
        return [*left, "ipsec_l3", destination_gateway, *right]

    def _path_between_groups(self, source_group: str, destination_group: str, source: dict[str, Any], destination: dict[str, Any]) -> list[str]:
        source_path = self._path_for_endpoint(source)
        destination_path = self._path_for_endpoint(destination)
        return self._routed_between_sites(
            source_path,
            self._gateway_site(source),
            destination_path,
            self._gateway_site(destination),
        )

    def decide_ip(self, source_ip: str, destination_ip: str, icmp_type: int | None = None) -> dict[str, Any]:
        source = self.endpoint_by_ip(source_ip)
        destination = self.endpoint_by_ip(destination_ip)
        if not source or not destination:
            return self._result("deny", "Endpoint khong thuoc source-of-truth.", [], None)
        return self.decide_packet(source["name"], destination["name"], icmp_type=icmp_type)

    def decide_packet(self, source_name: str, destination_name: str, icmp_type: int | None = None) -> dict[str, Any]:
        source = self.endpoint(source_name)
        destination = self.endpoint(destination_name)
        if source and destination and icmp_type == ICMP_ECHO_REPLY:
            reverse = self.decide(destination_name, source_name)
            if reverse["action"] == "allow":
                return {**reverse, "path": list(reversed(reverse["path"])), "reason": f"ICMP echo-reply cho phien duoc phep. {reverse['reason']}"}
        return self.decide(source_name, destination_name)

    def decide(self, source_name: str, destination_name: str) -> dict[str, Any]:
        source = self.endpoint(source_name)
        destination = self.endpoint(destination_name)
        if not source or not destination:
            return self._result("deny", "Khong tim thay source hoac destination trong policy.", [], None)

        if source["kind"] == "service" and destination["kind"] in {"user", "guest", "iot"}:
            site = self._gateway_site(destination)
            firewall = self._site_firewall(site)
            return self._result(
                "deny",
                "Stateful firewall chan ket noi moi tu Internet/partner service vao endpoint noi bo.",
                [source_name, self._internet_node(), firewall],
                firewall,
            )
        if source["kind"] == "service":
            return self._result("deny", "Service external khong duoc chu dong truy cap service khac.", [source_name, self._internet_node()], self._internet_node())

        if destination["kind"] == "service":
            return self._service_decision(source, destination)
        if destination["kind"] == "infrastructure_service":
            return self._infrastructure_service_decision(source, destination)
        if source["kind"] in {"guest", "iot"}:
            return self._enterprise_source_decision(source, destination)
        if source["kind"] == "infrastructure_service":
            return self._result("deny", "Infrastructure service khong duoc chu dong lateral movement.", [], None)

        source_group = str(source["group"])
        destination_group = str(destination["group"])
        source_path = self._path_for_endpoint(source)
        destination_path = self._path_for_endpoint(destination)

        if source_group == IT_SUPPORT_GROUP:
            return self._it_support_decision(source, destination)
        if destination_group == IT_SUPPORT_GROUP and source_group != IT_SUPPORT_GROUP:
            return self._result("deny", "User thuong khong duoc chu dong truy cap VLAN IT Support.", source_path, self._enforcement_for_group(source_group))

        if source_group == destination_group:
            if source_group == "project_2" and source.get("site") != destination.get("site"):
                return self._result(
                    "allow",
                    "Cung VLAN 93 qua MPLS L2VPN Primary; gateway 10.10.93.1 chi tai HQ. Backup la standby.",
                    self._project2_l2_path(source, destination),
                    None,
                )
            return self._result("allow", "Cho phep noi bo cung nhom/VLAN.", [*source_path, *list(reversed(destination_path))[1:]], None)

        if self.policies.get("isolate_hq_projects", False) and source_group in PROJECT_GROUPS and destination_group in PROJECT_GROUPS:
            return self._result(
                "deny",
                f"Bi chan boi segmentation giua VLAN {source['vlan']} va VLAN {destination['vlan']}.",
                source_path,
                self._enforcement_for_group(source_group),
            )

        return self._result("deny", "Mac dinh tu choi theo SDN Edge Policy.", source_path, self._enforcement_for_group(source_group))

    def _service_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        source_path = self._path_for_endpoint(source)
        site = self._gateway_site(source)
        firewall = self._site_firewall(site)
        service_name = str(destination["name"])
        if service_name == "hsocial" and self.policies.get("block_social_media", False):
            return self._result("deny", "Social Media bi chan tai stateful nftables firewall.", [*source_path, firewall], firewall)

        policy_flags = {
            "h90": "allow_voice",
            "hcall": "allow_call_app",
            "hzalo": "allow_zalo",
            "hinternet": "allow_general_internet",
        }
        if source.get("group") == "guest" and service_name == "hinternet":
            allowed = bool(self.policies.get("allow_guest_general_internet", False))
        else:
            allowed = bool(self.policies.get(policy_flags.get(service_name, ""), False))
        if not allowed:
            return self._result("deny", "Dich vu khong nam trong danh sach cho phep.", [*source_path, firewall], firewall)

        label = {
            "h90": "Partner PBX / Contact Center",
            "hcall": "Partner CRM",
            "hzalo": "Internet App",
            "hinternet": "General Internet",
        }.get(service_name, service_name)
        result = self._result(
            "allow",
            f"{label} duoc phep qua firewall cua site gateway {site}.",
            [*source_path, firewall, self._internet_node(), service_name],
            None,
        )
        if service_name == "h90":
            result["voice_flow_priority"] = bool(self.policies.get("voice_flow_priority", False))
        return result

    def _infrastructure_service_path(self, source: dict[str, Any], destination_name: str) -> list[str]:
        path = self._path_for_endpoint(source)
        site = self._gateway_site(source)
        if site == "branch":
            if not path or path[-1] != "dist_branch":
                path.append("dist_branch")
            path.extend(["ipsec_l3", "core_hq"])
        if not path or path[-1] != "core_hq":
            path.append("core_hq")
        return [*path, "infra_access", destination_name]

    def _infrastructure_service_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        source_group = str(source.get("group"))
        allowed: dict[str, set[str]] = {
            "guest": {"hdhcp", "hdns", "hntp"},
            "iot_hq": {"hdhcp", "hdns", "hntp", "hmonitor"},
            "iot_branch": {"hdhcp", "hdns", "hntp", "hmonitor"},
            "it_support": set(self.infrastructure_services),
            "project_1": {"hdhcp", "hdns", "hntp"},
            "project_2": {"hdhcp", "hdns", "hntp"},
            "project_3": {"hdhcp", "hdns", "hntp"},
            "project_4": {"hdhcp", "hdns", "hntp"},
        }
        if destination["name"] in allowed.get(source_group, set()):
            return self._result(
                "allow",
                "Infrastructure service duoc phep theo least-privilege policy.",
                self._infrastructure_service_path(source, str(destination["name"])),
                None,
            )
        return self._result("deny", "Infrastructure service khong duoc phep cho source group nay.", self._path_for_endpoint(source), self._enforcement_for_group(source_group))

    def _enterprise_source_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        source_group = str(source.get("group"))
        if source_group == "guest":
            if destination["kind"] == "service" and destination["name"] == "hinternet":
                return self._service_decision(source, destination)
            if destination["kind"] == "infrastructure_service":
                return self._infrastructure_service_decision(source, destination)
            return self._result("deny", "Guest chi duoc bootstrap services va General Internet.", self._path_for_endpoint(source), self._enforcement_for_group(source_group))
        if source_group in {"iot_hq", "iot_branch"}:
            if destination["kind"] == "infrastructure_service":
                return self._infrastructure_service_decision(source, destination)
            return self._result("deny", "IoT/UPS khong duoc truy cap user, partner service hoac Internet theo mac dinh.", self._path_for_endpoint(source), self._enforcement_for_group(source_group))
        return self._result("deny", "Enterprise zone khong co rule allow.", self._path_for_endpoint(source), self._enforcement_for_group(source_group))

    def _it_support_policy(self) -> dict[str, Any]:
        configured = self.policies.get("it_support_controlled_access") or {}
        return {
            "enabled": configured.get("enabled", self.policies.get("allow_it_support_controlled_access", False)),
            "source_group": configured.get("source_group", IT_SUPPORT_GROUP),
            "allow_icmp_to_managed_users": configured.get("allow_icmp_to_managed_users", True),
            "managed_user_groups": configured.get("managed_user_groups", sorted(PROJECT_GROUPS | {"iot_hq", "iot_branch"})),
            "allowed_services": configured.get("allowed_services", ["h90", "hcall", "hzalo", "hinternet"]),
            "denied_services": configured.get("denied_services", ["hsocial"]),
            "management_tcp_ports": configured.get("management_tcp_ports", [22, 443, 3389, 5985, 5986]),
        }

    def _it_support_decision(self, source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
        policy = self._it_support_policy()
        if not policy["enabled"]:
            return self._result("deny", "IT Support controlled access bi tat.", self._path_for_endpoint(source), "core_hq")
        if destination["kind"] == "service":
            if destination["name"] in set(policy["denied_services"]):
                return self._service_decision(source, destination)
            if destination["name"] in set(policy["allowed_services"]):
                return self._service_decision(source, destination)
            return self._result("deny", "IT Support least privilege: service khong duoc khai bao.", self._path_for_endpoint(source), "core_hq")
        if destination["kind"] == "infrastructure_service":
            return self._infrastructure_service_decision(source, destination)
        destination_group = str(destination.get("group"))
        if policy["allow_icmp_to_managed_users"] and destination_group in set(policy["managed_user_groups"]):
            return self._result(
                "allow",
                "IT Support duoc chu dong remote/support managed endpoint.",
                self._path_between_groups(IT_SUPPORT_GROUP, destination_group, source, destination),
                None,
            )
        return self._result("deny", "IT Support destination khong nam trong managed_user_groups.", self._path_for_endpoint(source), "core_hq")
