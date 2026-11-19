import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "Automated Meeting Minutes Generator" in data["message"]
    assert data["api_v1"] == "/api/v1"
    assert data["docs"] == "/docs"


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unprefixed_meetings_routes_are_consolidated():
    """Verify that duplicate unprefixed routes have been removed from the root
    and now reside strictly under /api/v1."""
    # Old unprefixed POST /meetings
    post_resp = client.post("/meetings", json={"title": "Old Route"})
    assert post_resp.status_code == 404

    # Old unprefixed GET /meetings
    get_resp = client.get("/meetings")
    assert get_resp.status_code == 404

    # Old unprefixed transcribe endpoint
    transcribe_resp = client.post("/meetings/fake-id/transcribe")
    assert transcribe_resp.status_code == 404


def test_cors_headers_present():
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    }
    response = client.options("/api/v1/meetings", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
