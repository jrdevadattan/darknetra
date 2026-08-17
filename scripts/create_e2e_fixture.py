from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from urllib.parse import urlparse

REQUIRED_CREDENTIAL_VARIABLES = (
    "DARKNETRA_E2E_ANALYST_A_PASSWORD",
    "DARKNETRA_E2E_ANALYST_B_PASSWORD",
    "DARKNETRA_E2E_BOOTSTRAP_PASSWORD",
)


class FixtureSafetyError(RuntimeError):
    pass


def _database_name(database_url: str) -> str:
    parsed = urlparse(database_url)
    return parsed.path.lstrip("/").split("/", maxsplit=1)[0]


def validate_fixture_environment(environment: Mapping[str, str]) -> None:
    if environment.get("DARKNETRA_ENVIRONMENT") != "test":
        raise FixtureSafetyError("fixture creation requires DARKNETRA_ENVIRONMENT=test")

    database_url = environment.get("DARKNETRA_DATABASE_URL", "")
    database_name = _database_name(database_url)
    if not database_name or "test" not in database_name.lower():
        raise FixtureSafetyError(
            "fixture creation requires a clearly test-scoped database name containing 'test'"
        )

    missing = [name for name in REQUIRED_CREDENTIAL_VARIABLES if not environment.get(name)]
    if missing:
        raise FixtureSafetyError(
            "missing synthetic credential environment variables: " + ", ".join(missing)
        )


def main() -> int:
    try:
        validate_fixture_environment(os.environ)
    except FixtureSafetyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    # Database fixture creation is added only after the destructive-safety contract is green.
    print(json.dumps({"status": "validated-test-fixture-environment"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
