"""Source-of-truth to Mininet runtime link contract for enterprise topology v7.

This module intentionally has no Mininet imports so validation can run on any
OS. The executable lab uses the same mapping on Ubuntu.
"""

from __future__ import annotations


RUNTIME_COLLAPSED_GATEWAYS = {
    "core_hq": "hq_l3_gateway",
    "dist_branch": "telesale_l3_gateway",
}

RUNTIME_BACKBONE_LINK_MAP = {
    frozenset(("access_floor1", "core_hq")): (
        ("access_floor1", "core_hq", "f1-eth99", "core-eth01", 1000, "1ms"),
    ),
    frozenset(("access_floor2", "core_hq")): (
        ("access_floor2", "core_hq", "f2-eth99", "core-eth02", 1000, "1ms"),
    ),
    frozenset(("infra_access", "core_hq")): (
        ("infra_access", "core_hq", "inf-eth99", "core-eth04", 1000, "1ms"),
    ),
    frozenset(("access_branch", "dist_branch")): (
        ("access_branch", "dist_branch", "br-eth99", "bd-eth01", 1000, "1ms"),
    ),

    # VLAN 93 primary L2VPN path.
    frozenset(("core_hq", "ce_hq1")): (
        ("core_hq", "ce_hq1", "core-eth93p", "ceh1-lan", 200, "2ms"),
    ),
    frozenset(("ce_hq1", "l2vpn_primary")): (
        ("ce_hq1", "l2vpn_primary", "ceh1-wan", "p93-hq", 200, "8ms"),
    ),
    frozenset(("l2vpn_primary", "ce_branch1")): (
        ("l2vpn_primary", "ce_branch1", "p93-br", "ceb1-wan", 200, "8ms"),
    ),
    frozenset(("ce_branch1", "dist_branch")): (
        ("ce_branch1", "dist_branch", "ceb1-lan", "bd-eth93p", 200, "2ms"),
    ),

    # VLAN 93 backup path. The customer attachment segments stay down until failover.
    frozenset(("core_hq", "ce_hq2")): (
        ("core_hq", "ce_hq2", "core-eth93b", "ceh2-lan", 200, "2ms"),
    ),
    frozenset(("ce_hq2", "l2vpn_backup")): (
        ("ce_hq2", "l2vpn_backup", "ceh2-wan", "b93-hq", 200, "8ms"),
    ),
    frozenset(("l2vpn_backup", "ce_branch2")): (
        ("l2vpn_backup", "ce_branch2", "b93-br", "ceb2-wan", 200, "8ms"),
    ),
    frozenset(("ce_branch2", "dist_branch")): (
        ("ce_branch2", "dist_branch", "ceb2-lan", "bd-eth93b", 200, "2ms"),
    ),

    # Core/Distribution to firewall inside links.
    frozenset(("core_hq", "fw_hq")): (
        ("core_hq", "hq_l3_gateway", "core-eth03", "hq_l3-eth0", 1000, "1ms"),
        ("hq_l3_gateway", "fw_hq", "hq_l3-eth1", "fw_hq-eth0", 200, "2ms"),
    ),
    frozenset(("fw_telesale", "dist_branch")): (
        ("fw_telesale", "telesale_l3_gateway", "fw_tel-eth0", "tele_l3-eth1", 200, "2ms"),
        ("telesale_l3_gateway", "dist_branch", "tele_l3-eth0", "bd-eth02", 1000, "1ms"),
    ),

    # Routed IPsec abstraction terminates on the two firewall namespaces.
    frozenset(("fw_hq", "ipsec_l3")): (
        ("fw_hq", "ipsec_l3", "fw_hq-eth2", "ipsec-hq", 200, "8ms"),
    ),
    frozenset(("ipsec_l3", "fw_telesale")): (
        ("ipsec_l3", "fw_telesale", "ipsec-br", "fw_tel-eth2", 200, "8ms"),
    ),

    # Site-local Internet breakout.
    frozenset(("fw_hq", "internet_zone")): (
        ("fw_hq", "internet_zone", "fw_hq-eth1", "inet-eth0", 100, "5ms"),
    ),
    frozenset(("fw_telesale", "internet_zone")): (
        ("fw_telesale", "internet_zone", "fw_tel-eth1", "inet-eth1", 100, "5ms"),
    ),
}


def source_truth_runtime_links(model: dict | None = None) -> list[tuple[str, str, str, str, int, str]]:
    """Expand declared infrastructure links into concrete Mininet links."""
    if model is None:
        from scripts.network_model import load_network_model

        model = load_network_model()

    infrastructure_names = set(model.get("infrastructure", {})) | set(model.get("switches", {}))
    generated_by_inventory = set(model.get("host_groups", {}))
    generated_by_inventory |= set(model.get("services", {}))
    generated_by_inventory |= set(model.get("infrastructure_services", {}))
    declared_backbone: set[frozenset[str]] = set()
    runtime_links: list[tuple[str, str, str, str, int, str]] = []

    for source, target, _kind in model.get("links", []):
        endpoints = {str(source), str(target)}
        key = frozenset(endpoints)
        if endpoints & generated_by_inventory:
            continue
        if not endpoints.issubset(infrastructure_names):
            raise ValueError(f"Source-of-truth link has unsupported runtime endpoint: {source}<->{target}")
        declared_backbone.add(key)
        try:
            runtime_links.extend(RUNTIME_BACKBONE_LINK_MAP[key])
        except KeyError as exc:
            raise ValueError(f"No Mininet runtime mapping for source-of-truth link: {source}<->{target}") from exc

    mapped_backbone = set(RUNTIME_BACKBONE_LINK_MAP)
    if declared_backbone != mapped_backbone:
        missing = sorted(mapped_backbone - declared_backbone, key=str)
        extra = sorted(declared_backbone - mapped_backbone, key=str)
        raise ValueError(f"Runtime backbone mapping mismatch: missing={missing}, extra={extra}")
    if any(len(left) > 15 or len(right) > 15 for _, _, left, right, _, _ in runtime_links):
        raise ValueError("Runtime interface name exceeds Linux 15-byte limit")
    return runtime_links
