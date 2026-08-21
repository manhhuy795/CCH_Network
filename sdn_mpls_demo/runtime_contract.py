"""Source-of-truth to Mininet runtime link contract.

The module intentionally has no Mininet imports so static validation can run
on Windows while Ubuntu topology runtime uses the same contract.
"""

from __future__ import annotations

RUNTIME_COLLAPSED_GATEWAYS = {
    "core_hq": "hq_l3_gateway",
    "dist_branch": "telesale_l3_gateway",
}

RUNTIME_BACKBONE_LINK_MAP = {
    frozenset(("access_floor1", "dist_hq_1")): (("access_floor1", "dist_hq_1", "f1-eth99", "d1-eth01", 1000, "1ms"),),
    frozenset(("access_floor2", "dist_hq_2")): (("access_floor2", "dist_hq_2", "f2-eth99", "d2-eth01", 1000, "1ms"),),
    frozenset(("infra_access", "dist_hq_1")): (("infra_access", "dist_hq_1", "inf-eth99", "d1-eth03", 1000, "1ms"),),
    frozenset(("dist_hq_1", "core_hq")): (("dist_hq_1", "core_hq", "d1-eth02", "core-eth01", 1000, "1ms"),),
    frozenset(("dist_hq_2", "core_hq")): (("dist_hq_2", "core_hq", "d2-eth02", "core-eth02", 1000, "1ms"),),
    frozenset(("dist_hq_2", "l2vpn_vpws40")): (("dist_hq_2", "l2vpn_vpws40", "d2-eth40", "pw40-hq", 200, "8ms"),),
    frozenset(("access_branch", "dist_branch")): (("access_branch", "dist_branch", "br-eth99", "bd-eth01", 1000, "1ms"),),
    frozenset(("dist_branch", "l2vpn_vpws40")): (("dist_branch", "l2vpn_vpws40", "bd-eth40", "pw40-br", 200, "8ms"),),
    frozenset(("core_hq", "ce_hq")): (
        ("core_hq", "hq_l3_gateway", "core-eth03", "hq_l3-eth0", 1000, "1ms"),
        ("hq_l3_gateway", "ce_hq", "hq_l3-eth1", "ce_hq-eth0", 200, "2ms"),
    ),
    frozenset(("ce_hq", "mpls_primary")): (("ce_hq", "mpls_primary", "ce_hq-eth1", "mpls-p-eth0", 100, "10ms"),),
    frozenset(("mpls_primary", "ce_telesale")): (("mpls_primary", "ce_telesale", "mpls-p-eth1", "ce_tel-eth1", 100, "10ms"),),
    frozenset(("ce_hq", "mpls_backup")): (("ce_hq", "mpls_backup", "ce_hq-eth2", "mpls-b-eth0", 100, "10ms"),),
    frozenset(("mpls_backup", "ce_telesale")): (("mpls_backup", "ce_telesale", "mpls-b-eth1", "ce_tel-eth2", 100, "10ms"),),
    frozenset(("ce_telesale", "dist_branch")): (
        ("ce_telesale", "telesale_l3_gateway", "ce_tel-eth0", "tele_l3-eth1", 200, "2ms"),
        ("telesale_l3_gateway", "dist_branch", "tele_l3-eth0", "bd-eth02", 1000, "1ms"),
    ),
    frozenset(("core_hq", "fw_hq")): (("hq_l3_gateway", "fw_hq", "hq_l3-eth2", "fw_hq-eth0", 200, "2ms"),),
    frozenset(("dist_branch", "fw_telesale")): (("telesale_l3_gateway", "fw_telesale", "tele_l3-eth2", "fw_tel-eth0", 200, "2ms"),),
    frozenset(("fw_hq", "internet_zone")): (("fw_hq", "internet_zone", "fw_hq-eth1", "inet-eth0", 100, "5ms"),),
    frozenset(("fw_telesale", "internet_zone")): (("fw_telesale", "internet_zone", "fw_tel-eth1", "inet-eth1", 100, "5ms"),),
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
