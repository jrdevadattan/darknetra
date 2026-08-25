import base64
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from darknetra_api.config import Settings, get_settings
from darknetra_api.main import create_app, create_production_app
from fastapi.testclient import TestClient

CRYPTO_ENV_NAMES = (
    "DARKNETRA_FIELD_KEY_V1_B64",
    "DARKNETRA_FIELD_KEYRING_B64_JSON",
    "DARKNETRA_FIELD_BLIND_INDEX_KEY_B64",
    "DARKNETRA_FIELD_ACTIVE_KEY_VERSION",
)


def encoded_random_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def valid_crypto_settings() -> dict[str, str]:
    return {
        "field_keyring_b64_json": json.dumps(
            {"v1": encoded_random_key(), "v2": encoded_random_key()}
        ),
        "field_blind_index_key_b64": encoded_random_key(),
        "field_active_key_version": "v2",
    }


def invalid_crypto_settings(case: str) -> Settings:
    valid = valid_crypto_settings()
    if case == "missing-key-source":
        valid["field_keyring_b64_json"] = ""
    elif case == "missing-blind-index-key":
        valid["field_blind_index_key_b64"] = ""
    elif case == "invalid-version":
        valid["field_active_key_version"] = "version-2"
        return Settings.model_construct(**valid)
    elif case == "duplicate-key-material":
        repeated = encoded_random_key()
        valid["field_keyring_b64_json"] = json.dumps({"v1": repeated, "v2": repeated})
    elif case == "unconfigured-active-version":
        valid["field_active_key_version"] = "v3"
    else:
        raise AssertionError(f"unknown test case: {case}")
    return Settings(**valid, _env_file=None)


def test_api_startup_accepts_sync_settings_provider() -> None:
    settings = Settings(**valid_crypto_settings(), _env_file=None)
    application = create_app(
        startup_settings_provider=lambda: settings,
        web_origin="https://sync.example",
    )

    with TestClient(application) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert {component["name"] for component in response.json()["components"]} == {
        "api",
        "sensitive-field-crypto",
    }


def test_api_startup_accepts_async_settings_provider() -> None:
    settings = Settings(**valid_crypto_settings(), _env_file=None)

    async def settings_provider() -> Settings:
        return settings

    application = create_app(
        startup_settings_provider=settings_provider,
        web_origin="https://async.example",
    )

    with TestClient(application) as client:
        assert client.get("/api/v1/health/ready").status_code == 200


def test_request_dependency_override_is_independent_from_startup_provider() -> None:
    startup = Settings(build_version="startup", **valid_crypto_settings(), _env_file=None)
    request = Settings(build_version="request", **valid_crypto_settings(), _env_file=None)
    application = create_app(
        startup_settings_provider=lambda: startup,
        web_origin="https://startup.example",
    )
    application.dependency_overrides[get_settings] = lambda: request

    try:
        with TestClient(application) as client:
            assert client.get("/api/v1/health/live").json()["version"] == "request"
    finally:
        application.dependency_overrides.clear()


def test_production_default_startup_provider_uses_runtime_environment(monkeypatch) -> None:
    monkeypatch.setenv("DARKNETRA_FIELD_KEY_V1_B64", encoded_random_key())
    monkeypatch.setenv("DARKNETRA_FIELD_BLIND_INDEX_KEY_B64", encoded_random_key())
    get_settings.cache_clear()
    try:
        application = create_production_app()
        with TestClient(application) as client:
            assert client.get("/api/v1/health/ready").status_code == 200
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "case",
    [
        "missing-key-source",
        "missing-blind-index-key",
        "invalid-version",
        "duplicate-key-material",
        "unconfigured-active-version",
    ],
)
def test_api_startup_fails_closed_for_invalid_crypto(
    case: str,
) -> None:
    settings = invalid_crypto_settings(case)
    application = create_app(
        startup_settings_provider=lambda: settings,
        web_origin="https://invalid-case.example",
    )

    with pytest.raises(ValueError), TestClient(application):
        pass


def test_injected_app_ignores_invalid_ambient_settings_and_uses_supplied_cors(
    monkeypatch,
) -> None:
    supplied = Settings(**valid_crypto_settings(), _env_file=None)
    intended_origin = "https://investigator.example"
    monkeypatch.setenv("DARKNETRA_FIELD_ACTIVE_KEY_VERSION", "invalid")
    get_settings.cache_clear()
    try:
        application = create_app(
            startup_settings_provider=lambda: supplied,
            web_origin=intended_origin,
        )
        with TestClient(application) as client:
            response = client.options(
                "/api/v1/health/live",
                headers={
                    "Origin": intended_origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == intended_origin
    finally:
        get_settings.cache_clear()


def test_custom_startup_provider_requires_explicit_web_origin() -> None:
    supplied = Settings(**valid_crypto_settings(), _env_file=None)

    with pytest.raises(TypeError, match="web_origin"):
        create_app(startup_settings_provider=lambda: supplied)  # type: ignore[call-arg]


def test_unrelated_unexpected_failure_keeps_fastapi_default_response() -> None:
    settings = Settings(**valid_crypto_settings(), _env_file=None)
    application = create_app(
        startup_settings_provider=lambda: settings,
        web_origin="https://failure.example",
    )

    @application.get("/api/v1/test-only-unrelated-failure")
    async def unrelated_failure() -> None:
        raise RuntimeError("unrelated synthetic failure")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/test-only-unrelated-failure")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Internal Server Error"
    assert "cache-control" not in response.headers


def worker_environment(settings: Settings) -> dict[str, str]:
    environment = os.environ.copy()
    for name in CRYPTO_ENV_NAMES:
        environment.pop(name, None)
    environment.update(
        {
            "DARKNETRA_FIELD_KEY_V1_B64": settings.field_key_v1_b64,
            "DARKNETRA_FIELD_KEYRING_B64_JSON": settings.field_keyring_b64_json,
            "DARKNETRA_FIELD_BLIND_INDEX_KEY_B64": settings.field_blind_index_key_b64,
            "DARKNETRA_FIELD_ACTIVE_KEY_VERSION": settings.field_active_key_version,
        }
    )
    api_root = Path(__file__).resolve().parents[2]
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(api_root), environment.get("PYTHONPATH")))
    )
    return environment


def import_worker(settings: Settings) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from darknetra_api.jobs.celery_app import celery_app; "
                "assert celery_app.conf.task_default_queue == 'ingest'"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=worker_environment(settings),
    )


def test_worker_import_accepts_valid_runtime_crypto() -> None:
    result = import_worker(Settings(**valid_crypto_settings(), _env_file=None))

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "case",
    [
        "missing-key-source",
        "missing-blind-index-key",
        "invalid-version",
        "duplicate-key-material",
        "unconfigured-active-version",
    ],
)
def test_worker_import_fails_closed_for_invalid_crypto(case: str) -> None:
    result = import_worker(invalid_crypto_settings(case))

    assert result.returncode != 0
