import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def test_compose_baseline_is_non_privileged_and_has_no_host_or_docker_socket_access() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    overlay = (ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
    combined = f"{compose}\n{overlay}"
    assert "privileged: true" not in combined
    assert "network_mode: host" not in combined
    assert "/var/run/docker.sock" not in combined


def test_compose_api_receives_authentication_security_configuration() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "DARKNETRA_WEB_ORIGIN:" in compose
    assert "DARKNETRA_JWT_SIGNING_KEY_B64:" in compose
    assert "${DARKNETRA_JWT_SIGNING_KEY_B64:-}" in compose


def test_local_example_keeps_browser_and_api_on_the_same_site() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "DARKNETRA_WEB_ORIGIN=http://localhost:3000" in example
    assert "NEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://localhost:8000" in example


def test_runtime_images_drop_root_privileges() -> None:
    api = (ROOT / "infrastructure" / "docker" / "api.Dockerfile").read_text(encoding="utf-8")
    web = (ROOT / "infrastructure" / "docker" / "web.Dockerfile").read_text(encoding="utf-8")
    assert "USER appuser" in api
    assert "USER appuser" in web
    assert "latest" not in api.lower()


def test_e2e_runtime_database_credential_is_shared_by_every_consumer() -> None:
    runtime_password = "rendered-contract-runtime-password"
    environment = {
        **os.environ,
        "DARKNETRA_JWT_SIGNING_KEY_B64": "runtime-only-test-key",
        "DARKNETRA_POSTGRES_RUNTIME_PASSWORD": runtime_password,
    }
    rendered = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.e2e.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    services = json.loads(rendered.stdout)["services"]

    assert services["postgres"]["environment"]["DARKNETRA_POSTGRES_RUNTIME_PASSWORD"] == (
        runtime_password
    )
    assert services["postgres"]["environment"]["POSTGRES_DB"] == "darknetra_e2e_test"
    assert services["db-bootstrap"]["environment"][
        "DARKNETRA_POSTGRES_RUNTIME_PASSWORD"
    ] == runtime_password
    assert services["db-bootstrap"]["environment"]["POSTGRES_DB"] == (
        "darknetra_e2e_test"
    )
    for service_name in ("api", "worker", "migrate"):
        database_url = services[service_name]["environment"]["DARKNETRA_DATABASE_URL"]
        assert urlsplit(database_url).password == runtime_password
        assert urlsplit(database_url).path == "/darknetra_e2e_test"
