import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]

EXECUTABLE_COMPOSE_FILES = {
    Path(".github/workflows/ci.yml"),
    Path(".github/workflows/plan02-task1.yml"),
    Path(".github/workflows/plan02-task13.yml"),
    Path(".github/workflows/plan02-task14.yml"),
    Path(".github/workflows/plan02-task2.yml"),
    Path(".github/workflows/task08-docker.yml"),
    Path(".github/workflows/task09-finalize-v2.yml"),
    Path(".github/workflows/task09-finalize-v3.yml"),
    Path(".github/workflows/task09-finalize-v4.yml"),
    Path(".github/workflows/task09-finalize.yml"),
    Path("Makefile"),
    Path("scripts/finalize_plan01_task9.sh"),
    Path("scripts/smoke.sh"),
}


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


def test_evidence_volume_is_shared_only_by_api_and_worker() -> None:
    runtime_password = "rendered-contract-runtime-password"
    environment = {
        **os.environ,
        "DARKNETRA_POSTGRES_RUNTIME_PASSWORD": runtime_password,
    }
    rendered = subprocess.run(
        ["docker", "compose", "-f", "docker-compose.yml", "config", "--format", "json"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    configuration = json.loads(rendered.stdout)
    services = configuration["services"]

    assert "evidence_store" in configuration["volumes"]
    for service_name in ("api", "worker"):
        mounts = services[service_name]["volumes"]
        assert mounts == [
            {
                "type": "volume",
                "source": "evidence_store",
                "target": "/var/lib/darknetra/evidence",
                "volume": {},
            }
        ]
        assert services[service_name]["environment"]["DARKNETRA_EVIDENCE_STORE_ROOT"] == (
            "/var/lib/darknetra/evidence"
        )

    for service_name in ("web", "postgres", "redis", "db-bootstrap", "migrate"):
        assert all(
            mount.get("source") != "evidence_store"
            for mount in services[service_name].get("volumes", [])
        )


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


def test_every_executable_compose_entrypoint_provisions_the_required_runtime_password() -> None:
    discovered = {
        path.relative_to(ROOT)
        for path in [
            *(ROOT / ".github" / "workflows").glob("*.yml"),
            *(ROOT / "scripts").glob("*.sh"),
            ROOT / "Makefile",
        ]
        if "docker compose" in path.read_text(encoding="utf-8")
    }
    assert discovered == EXECUTABLE_COMPOSE_FILES

    for relative_path in discovered:
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "DARKNETRA_POSTGRES_RUNTIME_PASSWORD" in content, relative_path

    workflow_paths = {
        path for path in discovered if path.parts[:2] == (".github", "workflows")
    }
    for relative_path in workflow_paths:
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "secrets.token_urlsafe" in content, relative_path
        assert "::add-mask::$RUNTIME_DB_PASSWORD" in content, relative_path

    for relative_path in {
        Path("Makefile"),
        Path("scripts/finalize_plan01_task9.sh"),
        Path("scripts/smoke.sh"),
    }:
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "secrets.token_urlsafe" in content, relative_path

    cleanup_workflows = {
        Path(".github/workflows/plan02-task1.yml"),
        Path(".github/workflows/plan02-task2.yml"),
        Path(".github/workflows/plan02-task13.yml"),
        Path(".github/workflows/plan02-task14.yml"),
    }
    for relative_path in cleanup_workflows:
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "cleanup-only-placeholder" in content, relative_path
