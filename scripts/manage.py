"""Cross-platform development commands; run with uv run --project backend python."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def environment() -> dict[str, str]:
    values = {
        key: value
        for key, value in dotenv_values(ROOT / ".env").items()
        if value is not None
    }
    values.update(os.environ)
    return values


def run(
    command: list[str], *, env: dict[str, str] | None = None, cwd: Path = ROOT
) -> None:
    subprocess.run(command, check=True, cwd=cwd, env=env or environment())


def docker() -> str:
    found = shutil.which("docker")
    if found:
        return found
    per_user = (
        Path(os.getenv("LOCALAPPDATA", ""))
        / "Programs/DockerDesktop/resources/bin/docker.exe"
    )
    if per_user.is_file():
        return str(per_user)
    raise SystemExit(
        "Docker is unavailable. Install/start Docker Desktop with its WSL2 Linux engine."
    )


def compose(*args: str) -> None:
    run(
        [
            docker(),
            "compose",
            "--env-file",
            str(ROOT / ".env"),
            "-f",
            str(ROOT / "infra/docker-compose.yml"),
            *args,
        ]
    )


def migrate(*, test: bool = False) -> None:
    env = environment()
    target = env[
        "DARKNETRA_TEST_DATABASE_URL" if test else "DARKNETRA_MIGRATION_DATABASE_URL"
    ]
    if test:
        from sqlalchemy.engine import make_url

        if "test" not in (make_url(target).database or "").casefold():
            raise SystemExit(
                "Test migration requires a database with 'test' in its name."
            )
    env["DARKNETRA_DATABASE_URL"] = env["DARKNETRA_MIGRATION_DATABASE_URL"] = target
    run([sys.executable, "scripts/migrate.py"], env=env, cwd=BACKEND)


def finalize_bootstrap(api: str) -> None:
    values = environment()
    origin = values.get("DARKNETRA_WEB_ORIGIN", "http://localhost:3000")
    with httpx.Client(base_url=api, timeout=20, headers={"Origin": origin}) as client:
        # Try the final password first, so repeated dev starts do not rotate credentials.
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "administrator",
                "password": values["DARKNETRA_ADMIN_PASSWORD"],
            },
        )
        if response.status_code == 200:
            return
        if response.status_code != 401:
            response.raise_for_status()
        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "administrator",
                "password": values["DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD"],
            },
        )
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = client.cookies["darknetra_csrf"]
        client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": values["DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD"],
                "new_password": values["DARKNETRA_ADMIN_PASSWORD"],
            },
        ).raise_for_status()
        print("Initial administrator password changed through the authenticated API.")


def wait_ready(api: str) -> None:
    deadline = time.monotonic() + 90
    with httpx.Client(timeout=3) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(api + "/api/v1/health/ready")
                if response.status_code == 200:
                    print("API ready: " + response.json()["status"])
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
    raise SystemExit(
        "API readiness timed out. Inspect docker compose logs api migrate."
    )


def export_openapi(*, check: bool = False) -> None:
    from darknetra.config import Settings
    from darknetra.main import create_app

    document = create_app(Settings(_env_file=ROOT / ".env")).openapi()
    encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path = ROOT / "docs/openapi.json"
    if check:
        if not path.exists() or path.read_text(encoding="utf-8") != encoded:
            raise SystemExit(
                "OpenAPI differs. Run make openapi and review the contract changes."
            )
        print("OpenAPI export matches the application.")
    else:
        path.write_text(encoded, encoding="utf-8", newline="\n")
        print(f"Exported {len(document['paths'])} API paths.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "dev",
            "up",
            "stop",
            "migrate",
            "test",
            "seed",
            "demo",
            "openapi",
            "check-openapi",
            "serve",
            "bootstrap",
        ],
    )
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if args.command in {"dev", "up"}:
        run([sys.executable, "scripts/setup.py"])
        compose("up", "-d", "--build", "api")
        wait_ready(args.api)
        compose("exec", "-T", "api", "python", "-m", "darknetra.cli", "bootstrap-admin")
        finalize_bootstrap(args.api)
        if args.command == "dev":
            run(
                [
                    sys.executable,
                    "backend/scripts/seed_synthetic_case.py",
                    "--api",
                    args.api,
                    "--if-missing",
                ]
            )
        print("DARKNETRA API: " + args.api + "/api/v1/docs")
    elif args.command == "stop":
        compose("stop")  # Preserve all persistent volumes.
    elif args.command == "migrate":
        migrate()
    elif args.command == "bootstrap":
        run([sys.executable, "-m", "darknetra.cli", "bootstrap-admin"])
        finalize_bootstrap(args.api)
    elif args.command == "test":
        migrate(test=True)
        run([sys.executable, "-m", "ruff", "check", "."], cwd=BACKEND)
        run([sys.executable, "-m", "ruff", "format", "--check", "."], cwd=BACKEND)
        run(
            [
                sys.executable,
                "-m",
                "mypy",
                "darknetra/tools",
                "darknetra/capture",
                "darknetra/policy",
            ],
            cwd=BACKEND,
        )
        run([sys.executable, "-m", "pytest", "-q"], cwd=BACKEND)
    elif args.command == "seed":
        run(
            [
                sys.executable,
                "backend/scripts/seed_synthetic_case.py",
                "--api",
                args.api,
                "--if-missing",
            ]
        )
    elif args.command == "demo":
        run(
            [
                sys.executable,
                "backend/scripts/seed_synthetic_case.py",
                "--api",
                args.api,
                "--if-missing",
            ]
        )
        run([sys.executable, "scripts/demo_walkthrough.py", "--api", args.api])
    elif args.command in {"openapi", "check-openapi"}:
        export_openapi(check=args.command == "check-openapi")
    elif args.command == "serve":
        run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "darknetra.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            ]
        )


if __name__ == "__main__":
    main()
