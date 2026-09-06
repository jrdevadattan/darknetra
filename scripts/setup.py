"""Generate local development configuration without printing credentials."""

import base64
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    path = ROOT / ".env"
    if path.exists():
        print("Existing .env preserved.")
        return
    app_password = secrets.token_hex(24)
    owner_password = secrets.token_hex(24)
    key = lambda: base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    values = {
        "DARKNETRA_ENV": "development",
        "DARKNETRA_DB_APP_PASSWORD": app_password,
        "DARKNETRA_DB_MIGRATE_PASSWORD": owner_password,
        "DARKNETRA_DATABASE_URL": f"postgresql+psycopg://darknetra_app:{app_password}@127.0.0.1:55432/darknetra",
        "DARKNETRA_MIGRATION_DATABASE_URL": f"postgresql+psycopg://darknetra_migrate:{owner_password}@127.0.0.1:55432/darknetra",
        "DARKNETRA_TEST_DATABASE_URL": f"postgresql+psycopg://darknetra_migrate:{owner_password}@127.0.0.1:55432/darknetra_test",
        "DARKNETRA_JWT_SIGNING_KEY_B64": key(),
        "DARKNETRA_FIELD_KEY_B64": key(),
        "DARKNETRA_VAULT_PATH": str(ROOT / "vault").replace("\\", "/"),
        "DARKNETRA_WEB_ORIGIN": "http://localhost:3000",
        "DARKNETRA_DEMO_MODE": "true",
        "DARKNETRA_OFFLINE_MODE": "true",
        "DARKNETRA_HARNESS_MODE": "deterministic",
        "DARKNETRA_BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "DARKNETRA_ADMIN_PASSWORD": secrets.token_urlsafe(24),
        "DARKNETRA_DEMO_ANALYST_PASSWORD": secrets.token_urlsafe(24),
    }
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for name, value in values.items():
            stream.write(f"{name}={value}\n")
    print("Created .env with unique local credentials. No credentials were printed.")


if __name__ == "__main__":
    main()
