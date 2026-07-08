import sys
from pathlib import Path

import pytest


def test_dashboard_api_topology_and_policy_endpoints():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.main import app

    client = TestClient(app)
    topology = client.get("/api/topology")
    policies = client.get("/api/policies")

    assert topology.status_code == 200
    assert policies.status_code == 200
    assert topology.json()["nodes"]
    assert topology.json()["links"]
    assert policies.json()["policies"]["block_social_media"] is True


def test_dashboard_serves_live_web_page():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "dashboard" / "backend"
    sys.path.insert(0, str(backend_root))

    from app.main import app

    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "CCH SDN Live Dashboard" in response.text
    assert "Ping" in response.text
    assert "Iperf" in response.text
