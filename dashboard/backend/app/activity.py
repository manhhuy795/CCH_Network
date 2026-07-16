from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DIR = REPO_ROOT / "sdn_mpls_demo" / "runtime"
ACTIVITY_FILE = RUNTIME_DIR / "dashboard_activity.jsonl"
CONTROLLER_EVENTS_FILE = RUNTIME_DIR / "events.jsonl"
_WRITE_LOCK = threading.Lock()
_SENSITIVE_KEYS = {"token", "authorization", "password", "secret", "x-cch-operator-token"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def append_event(
    *,
    component: str,
    event_type: str,
    message: str,
    severity: str = "info",
    source: str | None = None,
    destination: str | None = None,
    technical_detail: Any = None,
    task_id: str | None = None,
    user_action: str | None = None,
    status: str | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    duration_ms: float | None = None,
    result_summary: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    payload = {
        "id": uuid.uuid4().hex,
        "timestamp": utc_now(),
        "severity": severity,
        "component": component,
        "event_type": event_type,
        "source": source,
        "destination": destination,
        "message": message,
        "technical_detail": _sanitize(technical_detail),
        "task_id": task_id,
        "user_action": user_action,
        "status": status,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "result_summary": result_summary,
        "error_code": error_code,
    }
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        with ACTIVITY_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def record_operation(
    *,
    user_action: str,
    event_type: str,
    component: str,
    source: str | None,
    destination: str | None,
    started_at: str,
    started_monotonic: float,
    payload: dict[str, Any],
) -> dict[str, Any]:
    ended_at = utc_now()
    duration_ms = round((time.monotonic() - started_monotonic) * 1000, 2)
    error_code = str(payload.get("error_code") or "") or None
    completed = bool(payload.get("ok") or payload.get("measurement_completed") or error_code == "POLICY_DENIED")
    task_id = str(payload.get("session_id") or uuid.uuid4().hex)
    status = "success" if completed else "failed"
    message = str(payload.get("message_vi") or payload.get("message") or "Tác vụ hoàn tất.")
    severity = "info" if completed else "error"
    if error_code == "POLICY_DENIED":
        severity = "warning"
    event = append_event(
        component=component,
        event_type=event_type,
        message=message,
        severity=severity,
        source=source,
        destination=destination,
        technical_detail={
            "decision": payload.get("decision"),
            "result": payload.get("result"),
            "cleanup_warning": payload.get("cleanup_warning"),
            "parse_warning": payload.get("parse_warning"),
        },
        task_id=task_id,
        user_action=user_action,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        result_summary=message,
        error_code=error_code,
    )
    return {
        **payload,
        "task_id": task_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "task_status": status,
        "activity_id": event["id"],
    }


def _read_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    result: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            result.append(payload)
    return result


def activity_payload(limit: int = 300) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 1000))
    dashboard_events = _read_jsonl(ACTIVITY_FILE, safe_limit)
    controller_events = []
    for item in _read_jsonl(CONTROLLER_EVENTS_FILE, safe_limit):
        controller_events.append({
            "id": f"controller-{item.get('timestamp', uuid.uuid4().hex)}-{len(controller_events)}",
            "timestamp": item.get("timestamp"),
            "severity": "info",
            "component": "controller",
            "event_type": "FlowMod",
            "source": item.get("source"),
            "destination": item.get("destination"),
            "message": item.get("reason") or f"Controller {item.get('action', 'event')}",
            "technical_detail": _sanitize(item),
            "task_id": None,
        })
    events = sorted(
        [*dashboard_events, *controller_events],
        key=lambda item: str(item.get("timestamp") or ""),
        reverse=True,
    )[:safe_limit]
    tasks = [
        {
            "task_id": item.get("task_id"),
            "user_action": item.get("user_action"),
            "status": item.get("status"),
            "started_at": item.get("started_at"),
            "ended_at": item.get("ended_at"),
            "duration_ms": item.get("duration_ms"),
            "result_summary": item.get("result_summary"),
            "error_code": item.get("error_code"),
            "source": item.get("source"),
            "destination": item.get("destination"),
        }
        for item in dashboard_events
        if item.get("task_id")
    ]
    return {"events": events, "tasks": tasks[:safe_limit], "count": len(events)}
