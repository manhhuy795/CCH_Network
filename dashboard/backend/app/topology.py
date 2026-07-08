from __future__ import annotations

from .live_mininet import topology_payload


def get_topology(failed_links: set[str] | None = None) -> dict:
    return topology_payload()
