from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApiError(Exception):
    status_code: int
    error_code: str
    message_vi: str
    technical_detail: Any = None

    def __str__(self) -> str:
        return self.message_vi


ERROR_HTTP_STATUS = {
    "AUTH_REQUIRED": 401,
    "AUTH_INVALID": 403,
    "IPERF_BUSY": 409,
    "MININET_NOT_RUNNING": 503,
    "AGENT_NOT_READY": 503,
    "AGENT_DISCONNECTED": 503,
    "CONTROLLER_OFFLINE": 503,
    "OVS_UNAVAILABLE": 503,
    "IPERF_SERVER_FAILED": 503,
    "IPERF_CLIENT_FAILED": 503,
    "IPERF_PARSE_FAILED": 502,
    "AGENT_TIMEOUT": 504,
}


def error_payload(
    error_code: str,
    message_vi: str,
    request_id: str | None = None,
    technical_detail: Any = None,
) -> dict[str, Any]:
    payload = {
        "ok": False,
        "error_code": error_code,
        "message": message_vi,
        "message_vi": message_vi,
        "request_id": request_id,
    }
    if technical_detail is not None:
        payload["technical_detail"] = technical_detail
    return payload

