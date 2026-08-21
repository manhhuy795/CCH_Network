from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORT_FILE = REPO_ROOT / "runtime_reports" / "dashboard_preflight.json"


def _report_file() -> Path:
    configured = os.getenv("CCH_DASHBOARD_PREFLIGHT_REPORT")
    return Path(configured) if configured else DEFAULT_REPORT_FILE


def _age_seconds(value: Any) -> int | None:
    try:
        checked_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - checked_at).total_seconds()))
    except (TypeError, ValueError):
        return None


def dashboard_preflight_status() -> dict[str, Any]:
    path = _report_file()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "status": "not_run",
            "available": False,
            "message_vi": "Chưa có mẫu đo preflight của Mininet.",
            "report_path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
        }
    except (json.JSONDecodeError, OSError) as exc:
        return {
            "status": "invalid",
            "available": False,
            "message_vi": "Không đọc được báo cáo preflight Mininet.",
            "error_code": type(exc).__name__,
        }

    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return {
            "status": "invalid",
            "available": False,
            "message_vi": "Báo cáo preflight không đúng schema.",
            "error_code": "PREFLIGHT_SCHEMA_INVALID",
        }

    age = _age_seconds(payload.get("checked_at"))
    return {
        **payload,
        "available": True,
        "age_seconds": age,
        "stale": age is None or age > 3600,
    }
