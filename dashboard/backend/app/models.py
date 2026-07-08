from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HostPair(BaseModel):
    source: str = Field(..., examples=["h20"])
    destination: str = Field(..., examples=["hcall"])


class IperfRequest(HostPair):
    protocol: Literal["tcp", "udp"] = "tcp"
    seconds: int = Field(default=5, ge=1, le=60)


class PolicyToggleRequest(BaseModel):
    key: str
    enabled: bool


class LinkUpdateRequest(BaseModel):
    link_id: str
    bandwidth_mbps: float | None = None
    delay_ms: float | None = None
    loss_percent: float | None = None


class LinkStateRequest(BaseModel):
    link_id: str


class ApiMessage(BaseModel):
    ok: bool
    message: str
    data: dict[str, Any] | None = None

