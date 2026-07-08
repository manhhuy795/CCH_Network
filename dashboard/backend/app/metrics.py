from __future__ import annotations

from .live_mininet import current_metrics, iperf as run_iperf_live, ping as run_ping_live


def run_ping(source: str, destination: str, failed_links: set[str] | None = None) -> dict:
    return run_ping_live(source, destination)


def run_iperf(source: str, destination: str, protocol: str, seconds: int, failed_links: set[str] | None = None) -> dict:
    return run_iperf_live(source, destination, protocol, seconds)
