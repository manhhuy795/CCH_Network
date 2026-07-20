#!/usr/bin/env python3
"""Render and apply the two-site nftables policy used by the Mininet lab."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import load_vars
from scripts.network_model import load_network_model


REPO_ROOT = Path(__file__).resolve().parents[1]
SDN_POLICY_FILE = REPO_ROOT / "sdn_mpls_demo" / "policy.yml"
RUNTIME_RULESET_DIR = REPO_ROOT / "sdn_mpls_demo" / "runtime" / "firewalls"
NETNS_RUN_DIR = Path("/var/run/netns")
FIREWALL_NAMES = ("fw_hq", "fw_telesale")
NFT_FAMILY = "inet"
NFT_TABLE = "cch_filter"
_SAFE_IDENTIFIER = re.compile(r"^[a-zA-Z0-9_.:-]+$")


class FirewallPolicyError(RuntimeError):
    """Raised when source of truth or a live nftables operation is invalid."""


def _load_runtime_flags(path: Path = SDN_POLICY_FILE) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return dict(payload.get("policies", {}))


def _safe_identifier(value: Any, label: str) -> str:
    text = str(value or "")
    if not _SAFE_IDENTIFIER.fullmatch(text):
        raise FirewallPolicyError(f"{label} khong hop le: {text!r}")
    return text


def build_firewall_plans(
    config: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    runtime_flags: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build deterministic per-firewall plans entirely from repository source of truth."""
    config = config or load_vars()
    model = model or load_network_model()
    runtime_flags = runtime_flags or _load_runtime_flags()
    firewall_policy = config["firewall_policy"]
    defaults = firewall_policy["runtime_defaults"]
    sites = firewall_policy["sites"]
    applications = firewall_policy["shared_objects"]["applications"]
    vlan_subnets = {
        int(vlan["id"]): str(vlan["subnet"])
        for vlan in config["vlans"]
    }

    plans: dict[str, dict[str, Any]] = {}
    for site_name in sorted(sites):
        site = sites[site_name]
        firewall_name = _safe_identifier(site["firewall_name"], "firewall_name")
        runtime_interfaces = site["runtime_interfaces"]
        inside_interface = _safe_identifier(runtime_interfaces["inside"], "inside interface")
        outside_interface = _safe_identifier(runtime_interfaces["outside"], "outside interface")
        rules: list[dict[str, Any]] = []

        for policy in site.get("policies", []):
            enable_flag = str(policy["enable_flag"])
            if not bool(runtime_flags.get(enable_flag, False)):
                continue
            source_subnets = tuple(sorted({vlan_subnets[int(vlan)] for vlan in policy["sources"]}))
            for application_name in policy["applications"]:
                application = applications[application_name]
                service_name = str(application["runtime_service"])
                service = model["services"][service_name]
                comment = f"cch:{firewall_name}:{policy['name']}:{service_name}"
                rules.append({
                    "site": site_name,
                    "firewall": firewall_name,
                    "name": str(policy["name"]),
                    "action": str(policy["action"]).lower(),
                    "source_vlans": tuple(int(vlan) for vlan in policy["sources"]),
                    "source_subnets": source_subnets,
                    "destination_service": service_name,
                    "destination_ip": f"{service['ip']}/32",
                    "enable_flag": enable_flag,
                    "counter": bool(defaults["counter_enabled"]),
                    "comment": comment,
                })

        identities = [
            (
                rule["firewall"],
                rule["action"],
                rule["source_subnets"],
                rule["destination_ip"],
                rule["comment"],
            )
            for rule in rules
        ]
        if len(identities) != len(set(identities)):
            raise FirewallPolicyError(f"{firewall_name} co nftables rule trung lap")

        plans[firewall_name] = {
            "site": site_name,
            "firewall_name": firewall_name,
            "family": str(defaults["family"]),
            "table_name": str(defaults["table_name"]),
            "chain_priority": int(defaults["chain_priority"]),
            "input_policy": str(defaults["input_policy"]),
            "forward_policy": str(defaults["forward_policy"]),
            "output_policy": str(defaults["output_policy"]),
            "allow_established_related": bool(defaults["allow_established_related"]),
            "drop_invalid": bool(defaults["drop_invalid"]),
            "counter_enabled": bool(defaults["counter_enabled"]),
            "inside_interface": inside_interface,
            "outside_interface": outside_interface,
            "inside_logical_interface": str(site["inside_interface"]),
            "outside_logical_interface": str(site["outside_interface"]),
            "owned_subnets": tuple(sorted(str(prefix) for prefix in site["owned_subnets"])),
            "nat": dict(defaults["nat"]),
            "rules": tuple(rules),
        }

    if set(plans) != set(FIREWALL_NAMES):
        raise FirewallPolicyError(
            f"Chi duoc phep hai firewall {list(FIREWALL_NAMES)}, tim thay {sorted(plans)}"
        )
    return plans


def _set_literal(values: tuple[str, ...] | list[str]) -> str:
    return "{ " + ", ".join(values) + " }"


def render_nftables_ruleset(plan: dict[str, Any]) -> str:
    """Render one complete table. Applying it replaces only the CCH-owned table."""
    family = _safe_identifier(plan["family"], "nft family")
    table = _safe_identifier(plan["table_name"], "nft table")
    firewall = _safe_identifier(plan["firewall_name"], "firewall")
    inside = _safe_identifier(plan["inside_interface"], "inside interface")
    outside = _safe_identifier(plan["outside_interface"], "outside interface")
    priority = int(plan["chain_priority"])
    counter = "counter " if plan["counter_enabled"] else ""
    internal_subnets = _set_literal(list(plan["owned_subnets"]))
    lines = [
        f"table {family} {table} {{",
        "  set internal_subnets {",
        "    type ipv4_addr",
        "    flags interval",
        f"    elements = {internal_subnets}",
        "  }",
        "",
        "  chain input {",
        f"    type filter hook input priority {priority}; policy {plan['input_policy']};",
        f'    iifname "lo" {counter}accept comment "cch:{firewall}:input-loopback"',
    ]
    if plan["drop_invalid"]:
        lines.append(f'    ct state invalid {counter}drop comment "cch:{firewall}:input-invalid"')
    if plan["allow_established_related"]:
        lines.append(
            f'    ct state established,related {counter}accept comment "cch:{firewall}:input-established"'
        )
    lines.extend([
        (
            f'    iifname "{inside}" ip saddr @internal_subnets ip protocol icmp '
            f'icmp type echo-request {counter}accept comment "cch:{firewall}:input-inside-icmp"'
        ),
        f'    {counter}drop comment "cch:{firewall}:input-default-deny"',
        "  }",
        "",
        "  chain forward {",
        f"    type filter hook forward priority {priority}; policy {plan['forward_policy']};",
    ])
    if plan["drop_invalid"]:
        lines.append(f'    ct state invalid {counter}drop comment "cch:{firewall}:forward-invalid"')
    if plan["allow_established_related"]:
        lines.append(
            f'    ct state established,related {counter}accept comment "cch:{firewall}:forward-established"'
        )
    lines.append(
        f'    iifname "{outside}" oifname "{inside}" ip daddr @internal_subnets '
        f'ct state new {counter}drop comment "cch:{firewall}:deny-inbound-new"'
    )
    for rule in plan["rules"]:
        sources = _set_literal(list(rule["source_subnets"]))
        verdict = "accept" if rule["action"] == "allow" else "drop"
        lines.append(
            f'    iifname "{inside}" oifname "{outside}" ip saddr {sources} '
            f'ip daddr {rule["destination_ip"]} {counter}{verdict} comment "{rule["comment"]}"'
        )
    lines.extend([
        f'    {counter}drop comment "cch:{firewall}:forward-default-deny"',
        "  }",
        "",
        "  chain output {",
        f"    type filter hook output priority {priority}; policy {plan['output_policy']};",
        "  }",
        "}",
        "",
    ])
    if bool(plan["nat"].get("enabled")):
        raise FirewallPolicyError("NAT da bat nhung Phase 44 chua co runtime proof cho phep render NAT")
    return "\n".join(lines)


def write_rulesets(
    plans: dict[str, dict[str, Any]] | None = None,
    output_dir: Path = RUNTIME_RULESET_DIR,
) -> dict[str, Path]:
    plans = plans or build_firewall_plans()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for firewall_name, plan in plans.items():
        path = output_dir / f"{firewall_name}.nft"
        temporary = path.with_suffix(".nft.tmp")
        temporary.write_text(render_nftables_ruleset(plan), encoding="utf-8")
        temporary.replace(path)
        paths[firewall_name] = path
    return paths


def _node_command(node: Any, command: str) -> tuple[int, str]:
    marker = "__CCH_NFT_EXIT__="
    output = node.cmd(f"{command}; printf '\\n{marker}%s\\n' $?")
    match = re.search(rf"(?m)^{re.escape(marker)}(\d+)$", output)
    if not match:
        raise FirewallPolicyError(f"Khong doc duoc exit code nftables tren {node.name}: {output}")
    cleaned = re.sub(rf"(?m)^\s*{re.escape(marker)}\d+\s*$", "", output).strip()
    return int(match.group(1)), cleaned


def apply_to_mininet(net: Any, output_dir: Path = RUNTIME_RULESET_DIR) -> dict[str, dict[str, Any]]:
    """Syntax-check then replace the CCH table inside exactly two Mininet namespaces."""
    plans = build_firewall_plans()
    paths = write_rulesets(plans, output_dir)
    results: dict[str, dict[str, Any]] = {}
    for firewall_name in FIREWALL_NAMES:
        node = net.get(firewall_name)
        ruleset_path = paths[firewall_name].resolve()
        code, output = _node_command(node, f"nft --check --file '{ruleset_path}'")
        if code != 0:
            raise FirewallPolicyError(f"nft syntax check FAIL tren {firewall_name}: {output}")
        command = (
            f"nft delete table {NFT_FAMILY} {NFT_TABLE} 2>/dev/null || true; "
            f"nft --file '{ruleset_path}'"
        )
        code, output = _node_command(node, command)
        if code != 0:
            raise FirewallPolicyError(f"nft apply FAIL tren {firewall_name}: {output}")
        code, ruleset = _node_command(node, f"nft list table {NFT_FAMILY} {NFT_TABLE}")
        if code != 0:
            raise FirewallPolicyError(f"nft verify FAIL tren {firewall_name}: {ruleset}")
        results[firewall_name] = {
            "ok": True,
            "ruleset_path": str(ruleset_path),
            "rule_count": ruleset.count(" comment "),
            "ruleset": ruleset,
        }
    return results


def expose_named_firewall_namespaces(net: Any, run_dir: Path = NETNS_RUN_DIR) -> dict[str, str]:
    """Expose only firewall Mininet netns under stable names for operator evidence commands."""
    run_dir.mkdir(parents=True, exist_ok=True)
    exposed: dict[str, str] = {}
    for firewall_name in FIREWALL_NAMES:
        node = net.get(firewall_name)
        link = run_dir / firewall_name
        if link.exists() or link.is_symlink():
            link.unlink()
        target = f"/proc/{int(node.pid)}/ns/net"
        link.symlink_to(target)
        exposed[firewall_name] = target
    return exposed


def remove_named_firewall_namespaces(run_dir: Path = NETNS_RUN_DIR) -> None:
    for firewall_name in FIREWALL_NAMES:
        link = run_dir / firewall_name
        if link.is_symlink():
            link.unlink()


def _run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=check)


def apply_named_namespaces(output_dir: Path = RUNTIME_RULESET_DIR) -> dict[str, dict[str, Any]]:
    """Reload a running topology through its named firewall namespaces."""
    if sys.platform != "linux" or os.geteuid() != 0:
        raise FirewallPolicyError("Reload live firewall yeu cau Linux va quyen root")
    plans = build_firewall_plans()
    paths = write_rulesets(plans, output_dir)
    results: dict[str, dict[str, Any]] = {}
    for firewall_name in FIREWALL_NAMES:
        namespace_path = NETNS_RUN_DIR / firewall_name
        if not namespace_path.exists():
            raise FirewallPolicyError(f"Namespace {firewall_name} chua san sang")
        path = str(paths[firewall_name].resolve())
        prefix = ["ip", "netns", "exec", firewall_name, "nft"]
        checked = _run([*prefix, "--check", "--file", path])
        _run([*prefix, "delete", "table", NFT_FAMILY, NFT_TABLE], check=False)
        applied = _run([*prefix, "--file", path])
        listed = _run([*prefix, "list", "table", NFT_FAMILY, NFT_TABLE])
        results[firewall_name] = {
            "ok": True,
            "syntax_stdout": checked.stdout,
            "apply_stdout": applied.stdout,
            "rule_count": listed.stdout.count(" comment "),
            "ruleset": listed.stdout,
        }
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Render/reload CCH two-site nftables policy")
    parser.add_argument("--apply", action="store_true", help="Apply to named namespaces of a running topology")
    parser.add_argument("--output-dir", type=Path, default=RUNTIME_RULESET_DIR)
    args = parser.parse_args()
    try:
        if args.apply:
            result = apply_named_namespaces(args.output_dir)
        else:
            plans = build_firewall_plans()
            paths = write_rulesets(plans, args.output_dir)
            result = {
                name: {
                    "ruleset": str(path),
                    "rule_count": render_nftables_ruleset(plans[name]).count(" comment "),
                }
                for name, path in paths.items()
            }
    except (FirewallPolicyError, KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"FIREWALL ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
