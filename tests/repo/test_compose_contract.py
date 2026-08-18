from pathlib import Path

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


def test_runtime_images_drop_root_privileges() -> None:
    api = (ROOT / "infrastructure" / "docker" / "api.Dockerfile").read_text(encoding="utf-8")
    web = (ROOT / "infrastructure" / "docker" / "web.Dockerfile").read_text(encoding="utf-8")
    assert "USER appuser" in api
    assert "USER appuser" in web
    assert "latest" not in api.lower()
