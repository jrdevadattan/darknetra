import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "create_e2e_fixture.py"


def run_fixture_cli(**overrides: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("DARKNETRA_E2E_"):
            env.pop(key)
    env.update(overrides)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_fixture_cli_refuses_non_test_environment() -> None:
    result = run_fixture_cli(
        DARKNETRA_ENVIRONMENT="development",
        DARKNETRA_DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:55432/darknetra_e2e_test",
        DARKNETRA_E2E_ANALYST_A_PASSWORD="Synthetic-A-Password-42!",
        DARKNETRA_E2E_ANALYST_B_PASSWORD="Synthetic-B-Password-42!",
        DARKNETRA_E2E_BOOTSTRAP_PASSWORD="Synthetic-Bootstrap-42!",
    )

    assert result.returncode != 0
    assert "DARKNETRA_ENVIRONMENT=test" in result.stderr


def test_fixture_cli_refuses_non_test_scoped_database() -> None:
    result = run_fixture_cli(
        DARKNETRA_ENVIRONMENT="test",
        DARKNETRA_DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:5432/darknetra",
        DARKNETRA_E2E_ANALYST_A_PASSWORD="Synthetic-A-Password-42!",
        DARKNETRA_E2E_ANALYST_B_PASSWORD="Synthetic-B-Password-42!",
        DARKNETRA_E2E_BOOTSTRAP_PASSWORD="Synthetic-Bootstrap-42!",
    )

    assert result.returncode != 0
    assert "test-scoped database" in result.stderr


def test_fixture_cli_requires_synthetic_credentials_from_environment() -> None:
    result = run_fixture_cli(
        DARKNETRA_ENVIRONMENT="test",
        DARKNETRA_DATABASE_URL="postgresql+psycopg://user:pass@127.0.0.1:55432/darknetra_e2e_test",
    )

    assert result.returncode != 0
    assert "DARKNETRA_E2E_ANALYST_A_PASSWORD" in result.stderr
    assert "DARKNETRA_E2E_ANALYST_B_PASSWORD" in result.stderr
    assert "DARKNETRA_E2E_BOOTSTRAP_PASSWORD" in result.stderr
