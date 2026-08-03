from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_returns_api_information() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "South India Travel Guide API",
        "documentation": "/docs",
    }


def test_health_check_returns_status_and_version() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "version": "0.3.0",
    }
