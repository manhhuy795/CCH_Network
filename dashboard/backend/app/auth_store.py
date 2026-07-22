from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
AUTH_DB_ENV = "CCH_AUTH_DB"
SESSION_TTL_ENV = "CCH_AUTH_SESSION_TTL_SECONDS"
PBKDF2_ROUNDS = 600_000
LOGIN_LIMIT = 5
LOCK_SECONDS = 900
USERNAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,31}$")
ROLES = ("admin", "operator", "viewer", "auditor")

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "operator": frozenset({
        "dashboard.read",
        "runtime.execute",
        "runtime.link",
        "policy.toggle",
        "activity.read",
    }),
    "viewer": frozenset({"dashboard.read"}),
    "auditor": frozenset({"dashboard.read", "audit.read"}),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_text(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat()


def db_path() -> Path:
    configured = os.environ.get(AUTH_DB_ENV, "").strip()
    return Path(configured).expanduser() if configured else REPO_ROOT / "logs" / "auth.sqlite3"


def session_ttl_seconds() -> int:
    try:
        return max(300, min(int(os.environ.get(SESSION_TTL_ENV, "28800")), 604800))
    except ValueError:
        return 28800


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return connection


def initialize() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL CHECK(role IN ('admin','operator','viewer','auditor')),
                password_hash TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                disabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                revoked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(user_id);
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                request_id TEXT,
                actor_id TEXT,
                actor_username TEXT,
                actor_role TEXT,
                action TEXT NOT NULL,
                result TEXT NOT NULL,
                source_ip TEXT,
                detail_json TEXT
            );
            CREATE INDEX IF NOT EXISTS audit_events_time_idx ON audit_events(timestamp);
            """
        )


def validate_username(username: str) -> str:
    value = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError("Username phai co 3-32 ky tu, bat dau bang chu cai.")
    return value


def validate_role(role: str) -> str:
    if role not in ROLES:
        raise ValueError("Role khong hop le.")
    return role


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Mat khau phai co it nhat 12 ky tu.")
    if len(password) > 256:
        raise ValueError("Mat khau qua dai.")


def _hash_password(password: str, salt: bytes | None = None) -> str:
    validate_password(password)
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        rounds = int(rounds_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


def _hash_session(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _safe_detail(detail: Any) -> dict[str, Any] | None:
    if detail is None:
        return None
    if isinstance(detail, dict):
        return {str(key): "[REDACTED]" if str(key).lower() in {"password", "token", "authorization", "secret"} else value for key, value in detail.items()}
    return {"value": str(detail)}


def audit(
    *,
    action: str,
    result: str,
    request_id: str | None = None,
    actor: dict[str, Any] | None = None,
    source_ip: str | None = None,
    detail: Any = None,
) -> None:
    initialize()
    actor = actor or {}
    payload = json.dumps(_safe_detail(detail), ensure_ascii=False, separators=(",", ":"))
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO audit_events
            (id, timestamp, request_id, actor_id, actor_username, actor_role, action, result, source_ip, detail_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                utc_text(),
                request_id,
                actor.get("id"),
                actor.get("username"),
                actor.get("role"),
                action,
                result,
                source_ip,
                payload,
            ),
        )


def _public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "disabled": bool(row["disabled"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_login_at": row["last_login_at"],
    }


def list_users() -> list[dict[str, Any]]:
    initialize()
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM users ORDER BY username").fetchall()
    return [_public_user(row) for row in rows]


def create_user(username: str, password: str, role: str) -> dict[str, Any]:
    initialize()
    username = validate_username(username)
    role = validate_role(role)
    validate_password(password)
    now = utc_text()
    user = {
        "id": uuid.uuid4().hex,
        "username": username,
        "role": role,
        "password_hash": _hash_password(password),
        "created_at": now,
        "updated_at": now,
    }
    with _connect() as connection:
        connection.execute(
            "INSERT INTO users (id, username, role, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], username, role, user["password_hash"], now, now),
        )
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    return _public_user(row)


def _find_user(connection: sqlite3.Connection, username: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def login(username: str, password: str, *, request_id: str | None, source_ip: str | None) -> dict[str, Any]:
    initialize()
    try:
        username = validate_username(username)
    except ValueError:
        username = username.strip().lower()
    now = utc_now()
    with _connect() as connection:
        row = _find_user(connection, username)
        locked_until = None if not row else row["locked_until"]
        if row and locked_until:
            try:
                if datetime.fromisoformat(locked_until) > now:
                    connection.commit()
                    audit(action="login", result="locked", request_id=request_id, source_ip=source_ip, detail={"username": username})
                    return {"ok": False, "error_code": "AUTH_LOCKED"}
            except ValueError:
                pass

        valid = bool(row) and not bool(row["disabled"]) and _verify_password(password, row["password_hash"])
        if not valid:
            if row:
                failures = int(row["failed_attempts"]) + 1
                locked = utc_text(now + timedelta(seconds=LOCK_SECONDS)) if failures >= LOGIN_LIMIT else None
                connection.execute(
                    "UPDATE users SET failed_attempts = ?, locked_until = ?, updated_at = ? WHERE id = ?",
                    (failures, locked, utc_text(now), row["id"]),
                )
            connection.commit()
            audit(action="login", result="failed", request_id=request_id, source_ip=source_ip, detail={"username": username})
            return {"ok": False, "error_code": "AUTH_INVALID"}

        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(24)
        expires = now + timedelta(seconds=session_ttl_seconds())
        connection.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = ?, updated_at = ? WHERE id = ?",
            (utc_text(now), utc_text(now), row["id"]),
        )
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
            (_hash_session(token), row["id"], utc_text(now), utc_text(expires), utc_text(now)),
        )
        user = _public_user(connection.execute("SELECT * FROM users WHERE id = ?", (row["id"],)).fetchone())
    audit(action="login", result="success", request_id=request_id, actor=user, source_ip=source_ip)
    return {"ok": True, "token": token, "csrf_token": csrf_token, "expires_at": utc_text(expires), "user": user}


def _principal_from_row(row: sqlite3.Row, session_token: str | None = None) -> dict[str, Any]:
    result = _public_user(row)
    result["permissions"] = sorted(ROLE_PERMISSIONS[row["role"]])
    result["auth_method"] = "session"
    if session_token:
        result["_session_token"] = session_token
    return result


def session_principal(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    initialize()
    now = utc_now()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT users.* FROM sessions JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.revoked_at IS NULL
            """,
            (_hash_session(token),),
        ).fetchone()
        if not row:
            return None
        session = connection.execute("SELECT expires_at FROM sessions WHERE token_hash = ?", (_hash_session(token),)).fetchone()
        if not session or datetime.fromisoformat(session["expires_at"]) <= now or row["disabled"]:
            connection.execute("UPDATE sessions SET revoked_at = ? WHERE token_hash = ?", (utc_text(now), _hash_session(token)))
            return None
        connection.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (utc_text(now), _hash_session(token)))
        return _principal_from_row(row, token)


def revoke_session(token: str | None, *, request_id: str | None, actor: dict[str, Any] | None, source_ip: str | None) -> None:
    if token:
        initialize()
        with _connect() as connection:
            connection.execute("UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL", (utc_text(), _hash_session(token)))
    audit(action="logout", result="success", request_id=request_id, actor=actor, source_ip=source_ip)


def rotate_session(token: str, *, request_id: str | None, actor: dict[str, Any], source_ip: str | None) -> dict[str, Any] | None:
    principal = session_principal(token)
    if not principal:
        return None
    revoke_session(token, request_id=request_id, actor=actor, source_ip=source_ip)
    return _issue_session(actor)


def _issue_session(actor: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    expires = now + timedelta(seconds=session_ttl_seconds())
    with _connect() as connection:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
            (_hash_session(token), actor["id"], utc_text(now), utc_text(expires), utc_text(now)),
        )
    return {"ok": True, "token": token, "csrf_token": csrf_token, "expires_at": utc_text(expires), "user": actor}


def update_role(username: str, role: str) -> dict[str, Any]:
    username = validate_username(username)
    role = validate_role(role)
    initialize()
    with _connect() as connection:
        connection.execute("UPDATE users SET role = ?, updated_at = ? WHERE username = ?", (role, utc_text(), username))
        row = _find_user(connection, username)
        if not row:
            raise KeyError("Khong tim thay user.")
        return _public_user(row)


def set_disabled(username: str, disabled: bool) -> dict[str, Any]:
    username = validate_username(username)
    initialize()
    with _connect() as connection:
        connection.execute("UPDATE users SET disabled = ?, updated_at = ? WHERE username = ?", (int(disabled), utc_text(), username))
        row = _find_user(connection, username)
        if not row:
            raise KeyError("Khong tim thay user.")
        if disabled:
            connection.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (utc_text(), row["id"]))
        return _public_user(row)


def change_password(username: str, password: str) -> dict[str, Any]:
    username = validate_username(username)
    validate_password(password)
    initialize()
    with _connect() as connection:
        connection.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?", (_hash_password(password), utc_text(), username))
        row = _find_user(connection, username)
        if not row:
            raise KeyError("Khong tim thay user.")
        connection.execute("UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL", (utc_text(), row["id"]))
        return _public_user(row)


def audit_events(limit: int = 200) -> list[dict[str, Any]]:
    initialize()
    limit = max(1, min(limit, 1000))
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    result = []
    for row in rows:
        try:
            detail = json.loads(row["detail_json"] or "null")
        except json.JSONDecodeError:
            detail = None
        result.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "request_id": row["request_id"],
            "actor_id": row["actor_id"],
            "actor_username": row["actor_username"],
            "actor_role": row["actor_role"],
            "action": row["action"],
            "result": row["result"],
            "source_ip": row["source_ip"],
            "detail": detail,
        })
    return result


def has_permission(principal: dict[str, Any], permission: str) -> bool:
    permissions = principal.get("permissions") or ROLE_PERMISSIONS.get(principal.get("role"), frozenset())
    return "*" in permissions or permission in permissions
