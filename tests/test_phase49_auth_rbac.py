from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "dashboard" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient

from app import auth_store
from app.main import app


def make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CCH_AUTH_DB", str(tmp_path / "auth.sqlite3"))
    monkeypatch.delenv("CCH_DASHBOARD_OPERATOR_TOKEN", raising=False)
    auth_store.initialize()
    return TestClient(app)


def create_user(username: str, role: str) -> str:
    password = f"Phase49-{username}-" + ("x" * 16) + "!"
    auth_store.create_user(username, password, role)
    return password


def login(client: TestClient, username: str, password: str):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return client.cookies.get("cch_csrf")


def test_login_session_csrf_and_logout(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    password = create_user("admin", "admin")
    assert client.get("/api/topology").status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401
    csrf = login(client, "admin", password)
    assert csrf
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "admin"
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CCH-CSRF": csrf}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_role_matrix_is_enforced_server_side(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    viewer_password = create_user("viewer", "viewer")
    csrf = login(client, "viewer", viewer_password)
    assert client.get("/api/topology").status_code == 200
    assert client.post(
        "/api/test/ping",
        json={"source": "h20_01", "destination": "h90"},
        headers={"X-CCH-CSRF": csrf},
    ).status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_auditor_can_read_audit_but_cannot_run_runtime(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    password = create_user("auditor", "auditor")
    csrf = login(client, "auditor", password)
    assert client.get("/api/admin/audit").status_code == 200
    assert client.post(
        "/api/test/ping",
        json={"source": "h20_01", "destination": "h90"},
        headers={"X-CCH-CSRF": csrf},
    ).status_code == 403


def test_operator_token_is_machine_auth_and_not_admin(monkeypatch, tmp_path):
    monkeypatch.setenv("CCH_AUTH_DB", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("CCH_DASHBOARD_OPERATOR_TOKEN", "runtime-only-test-token")
    client = TestClient(app)
    headers = {"X-CCH-Operator-Token": "runtime-only-test-token"}
    assert client.get("/api/topology", headers=headers).status_code == 200
    assert client.get("/api/admin/users", headers=headers).status_code == 403


def test_audit_payload_never_contains_password_or_session_token(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    password = create_user("admin", "admin")
    csrf = login(client, "admin", password)
    response = client.get("/api/admin/audit")
    assert response.status_code == 200
    raw = json.dumps(response.json())
    assert password not in raw
    assert "cch_session" not in raw
    assert client.post("/api/auth/logout", headers={"X-CCH-CSRF": csrf}).status_code == 200


def test_frontend_does_not_store_operator_token():
    client_source = (REPO_ROOT / "dashboard" / "frontend" / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    app_source = (REPO_ROOT / "dashboard" / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "localStorage" not in client_source
    assert "getOperatorToken" not in app_source
    assert "credentials: \"include\"" in client_source
    assert "X-CCH-CSRF" in client_source
