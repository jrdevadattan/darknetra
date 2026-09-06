"""Restore only into a new database and a new directory; verify all content hashes."""

import argparse
import csv
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

from backup import audit_operation, compose_command, digest
from manage import environment


def verify_archive(backup: Path) -> None:
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "darknetra-backup-v1" or set(
        manifest.get("files", {})
    ) != {"database.dump", "vault.tar"}:
        raise ValueError("Unsupported backup manifest")
    for name, expected in manifest["files"].items():
        path = backup / name
        if (
            digest(path) != expected["sha256"]
            or path.stat().st_size != expected["size"]
        ):
            raise ValueError("Backup integrity mismatch: " + name)


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Restore directory must not exist")
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            resolved = (destination / member.name).resolve()
            if not resolved.is_relative_to(destination) or not (
                member.isfile() or member.isdir()
            ):
                raise ValueError("Unsafe archive member")
        destination.mkdir(parents=True, exist_ok=False)
        bundle.extractall(destination, filter="data")


def restore(backup: Path, database: str, vault: Path) -> int:
    if not re.fullmatch(r"darknetra_restore_[a-z0-9_]{1,40}", database):
        raise ValueError("Use a fresh database named darknetra_restore_<name>")
    backup, vault = backup.resolve(), vault.resolve()
    verify_archive(backup)
    if vault.exists():
        raise ValueError("Restore directory must not exist")
    # createdb refuses an existing database. Never use --clean or drop a database.
    subprocess.run(
        compose_command(
            "exec", "-T", "postgres", "createdb", "-U", "darknetra_migrate", database
        ),
        check=True,
        env=environment(),
    )
    with (backup / "database.dump").open("rb") as stream:
        subprocess.run(
            compose_command(
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "-U",
                "darknetra_migrate",
                "--exit-on-error",
                "--no-owner",
                "-d",
                database,
            ),
            stdin=stream,
            check=True,
            env=environment(),
        )
    safe_extract(backup / "vault.tar", vault)
    query = "SELECT storage_key,sha256 FROM evidence UNION SELECT storage_key,split_part(storage_key,'/',3) FROM derivatives UNION SELECT artifact->>'storage_key',artifact->>'sha256' FROM reports CROSS JOIN LATERAL jsonb_each(reports.includes->'artifacts') AS items(name,artifact)"
    result = subprocess.run(
        compose_command(
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "darknetra_migrate",
            "-d",
            database,
            "--csv",
            "-c",
            query,
        ),
        capture_output=True,
        check=True,
        env=environment(),
        text=True,
    )
    count = 0
    for row in csv.DictReader(io.StringIO(result.stdout)):
        key = row["storage_key"]
        if not re.fullmatch(r"[0-9a-f-]{36}/[0-9a-f]{2}/[0-9a-f]{64}", key):
            raise ValueError("Invalid restored storage key")
        path = (vault / key).resolve()
        if (
            not path.is_relative_to(vault)
            or not path.is_file()
            or digest(path) != row["sha256"]
        ):
            raise ValueError("Restored content hash mismatch")
        count += 1
    audit_operation(
        "backup.restored",
        {"verified_blobs": count, "manifest_sha256": digest(backup / "manifest.json")},
        database=database,
    )
    print(
        f"Restored into {database}; verified {count} original and derivative blobs. Active API configuration is unchanged."
    )
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--database", required=True)
    parser.add_argument("--vault", required=True, type=Path)
    args = parser.parse_args()
    restore(args.backup, args.database, args.vault)
