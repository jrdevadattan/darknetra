"""Back up this Compose database and immutable vault to a new local directory."""

import argparse
import asyncio
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from manage import ROOT, docker, environment


def compose_command(*args: str) -> list[str]:
    return [
        docker(),
        "compose",
        "--env-file",
        str(ROOT / ".env"),
        "-f",
        str(ROOT / "infra/docker-compose.yml"),
        *args,
    ]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def audit_operation(action: str, detail: dict, database: str | None = None) -> None:
    import darknetra.models  # noqa: F401
    from darknetra.audit.service import record
    from darknetra.auth.actor import Actor
    from darknetra.config import Settings
    from darknetra.db import build_engine, build_session_factory
    from sqlalchemy.engine import make_url

    settings = Settings(_env_file=ROOT / ".env")
    if database:
        settings.database_url = (
            make_url(settings.migration_database_url or settings.database_url)
            .set(database=database)
            .render_as_string(hide_password=False)
        )

    async def write():
        engine = build_engine(settings)
        try:
            async with build_session_factory(engine)() as db:
                await record(
                    db, actor=Actor("SYSTEM", None), action=action, detail=detail
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(write())


def backup(output: Path) -> Path:
    target = output.resolve() / datetime.now(UTC).strftime("darknetra-%Y%m%dT%H%M%S%fZ")
    target.mkdir(parents=True, exist_ok=False)
    audit_operation("backup.started", {"name": target.name})
    with (target / "database.dump").open("xb") as stream:
        subprocess.run(
            compose_command(
                "exec",
                "-T",
                "postgres",
                "pg_dump",
                "-U",
                "darknetra_migrate",
                "-Fc",
                "darknetra",
            ),
            stdout=stream,
            check=True,
            env=environment(),
        )
    # The database snapshot precedes the append-only vault copy. Every committed
    # reference in the dump therefore already exists when the archive is read.
    with (target / "vault.tar").open("xb") as stream:
        subprocess.run(
            compose_command(
                "exec",
                "-T",
                "api",
                "tar",
                "-C",
                "/var/lib/darknetra/vault",
                "-cf",
                "-",
                ".",
            ),
            stdout=stream,
            check=True,
            env=environment(),
        )
    manifest = {
        "format": "darknetra-backup-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "files": {
            name: {
                "sha256": digest(target / name),
                "size": (target / name).stat().st_size,
            }
            for name in ("database.dump", "vault.tar")
        },
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    audit_operation(
        "backup.completed",
        {"name": target.name, "manifest_sha256": digest(target / "manifest.json")},
    )
    print("Backup written with SHA-256 manifest: " + str(target))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "backups")
    backup(parser.parse_args().output)
