from __future__ import annotations

from .live_mininet import policy_payload


def get_policy_payload() -> dict:
    return policy_payload()


def toggle_policy(key: str, enabled: bool) -> dict:
    payload = policy_payload()
    if key not in payload["policies"]:
        raise KeyError(f"Khong co policy: {key}")
    payload["policies"][key] = enabled
    return payload["policies"]
