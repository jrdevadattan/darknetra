from darknetra_api.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_live_health_contract() -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "dev"}


def test_ready_health_contract() -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "version": "dev",
        "components": [{"name": "api", "status": "ready"}],
    }


def test_openapi_identity_is_darknetra() -> None:
    document = client.get("/openapi.json").json()
    assert document["info"]["title"] == "DARKNETRA API"
    assert document["info"]["version"] == "0.1.0"
