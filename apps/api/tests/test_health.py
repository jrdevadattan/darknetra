import base64
import secrets
from collections.abc import Iterator

import pytest
from darknetra_api.config import Settings, get_settings
from darknetra_api.main import create_app
from fastapi.testclient import TestClient

TEST_BUILD_VERSION = "health-contract-test"


def _test_settings() -> Settings:
    return Settings(
        build_version=TEST_BUILD_VERSION,
        field_key_v1_b64=base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        field_blind_index_key_b64=base64.b64encode(secrets.token_bytes(32)).decode("ascii"),
        _env_file=None,
    )


app = create_app(
    startup_settings_provider=_test_settings,
    web_origin="http://localhost:3000",
)


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
        "components": [
            {"name": "api", "status": "ready"},
            {"name": "sensitive-field-crypto", "status": "ready"},
        ],
    }


def test_openapi_identity_is_darknetra(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    assert document["info"]["title"] == "DARKNETRA API"
    assert document["info"]["version"] == "0.1.0"
