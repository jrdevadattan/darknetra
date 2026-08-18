from collections.abc import Iterator

import pytest
from darknetra_api.config import Settings, get_settings
from darknetra_api.main import app
from fastapi.testclient import TestClient

TEST_BUILD_VERSION = "health-contract-test"


def _test_settings() -> Settings:
    return Settings(build_version=TEST_BUILD_VERSION)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = _test_settings
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_live_health_contract(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": TEST_BUILD_VERSION}


def test_ready_health_contract(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "version": TEST_BUILD_VERSION,
        "components": [{"name": "api", "status": "ready"}],
    }


def test_openapi_identity_is_darknetra(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    assert document["info"]["title"] == "DARKNETRA API"
    assert document["info"]["version"] == "0.1.0"
