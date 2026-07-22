from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


SAFE_ID_PATTERN = r"^[A-Za-z0-9_.:-]+$"


class HostPair(BaseModel):
    source: str = Field(..., pattern=SAFE_ID_PATTERN, examples=["h20_01"])
    destination: str = Field(..., pattern=SAFE_ID_PATTERN, examples=["hcall"])

    @field_validator("source", "destination")
    @classmethod
    def reject_shell_metacharacters(cls, value: str) -> str:
        if any(item in value for item in (";", "&", "|", "$", "`", "\\", "/", "\n", "\r")):
            raise ValueError("endpoint id contains unsafe characters")
        return value


class IperfRequest(HostPair):
    protocol: Literal["tcp", "udp"] = "tcp"
    seconds: int = Field(default=5, ge=1, le=30)


class ClusterTestRequest(BaseModel):
    cluster: Literal["project_a", "project_b", "project_c", "telesale", "backoffice", "it_support"] = "project_a"
    seconds: int = Field(default=3, ge=1, le=20)


class PolicyToggleRequest(BaseModel):
    key: str = Field(..., pattern=SAFE_ID_PATTERN)
    enabled: bool


class LinkUpdateRequest(BaseModel):
    link_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    bandwidth_mbps: float | None = None
    delay_ms: float | None = None
    loss_percent: float | None = None


class LinkStateRequest(BaseModel):
    link_id: str = Field(..., pattern=SAFE_ID_PATTERN)


class ApiMessage(BaseModel):
    ok: bool
    message: str
    data: dict[str, Any] | None = None


class LoginRequest(BaseModel):
    username: str = Field(..., pattern=r"^[A-Za-z][A-Za-z0-9_.-]{2,31}$")
    password: str = Field(..., min_length=1, max_length=256)


class UserCreateRequest(BaseModel):
    username: str = Field(..., pattern=r"^[A-Za-z][A-Za-z0-9_.-]{2,31}$")
    password: str = Field(..., min_length=12, max_length=256)
    role: Literal["admin", "operator", "viewer", "auditor"] = "viewer"


class RoleUpdateRequest(BaseModel):
    role: Literal["admin", "operator", "viewer", "auditor"]


class PasswordUpdateRequest(BaseModel):
    password: str = Field(..., min_length=12, max_length=256)


class UserStatusUpdateRequest(BaseModel):
    disabled: bool
