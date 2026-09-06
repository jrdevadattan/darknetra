"""Offline operation checks: archive integrity, path safety and contract changes."""

import io
import json
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from backup import digest  # noqa: E402
from check_openapi_compat import breaking_changes  # noqa: E402
from restore import safe_extract, verify_archive  # noqa: E402


def test_backup_detects_corruption(tmp_path):
    for name in ("database.dump", "vault.tar"):
        (tmp_path / name).write_bytes(b"SYNTHETIC backup")
    manifest = {
        "format": "darknetra-backup-v1",
        "files": {
            name: {"sha256": digest(tmp_path / name), "size": (tmp_path / name).stat().st_size}
            for name in ("database.dump", "vault.tar")
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    verify_archive(tmp_path)
    (tmp_path / "vault.tar").write_bytes(b"SYNTHETIC corrupted")
    with pytest.raises(ValueError, match="mismatch"):
        verify_archive(tmp_path)


@pytest.mark.parametrize(
    "name,symlink", [("../escape", False), ("/absolute", False), ("link", True)]
)
def test_restore_refuses_unsafe_archive_paths(tmp_path, name, symlink):
    archive = tmp_path / "vault.tar"
    with tarfile.open(archive, "w") as bundle:
        member = tarfile.TarInfo(name)
        if symlink:
            member.type, member.linkname = tarfile.SYMTYPE, "../escape"
        bundle.addfile(member, io.BytesIO(b""))
    with pytest.raises(ValueError, match="Unsafe"):
        safe_extract(archive, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_contract_checker_rejects_removed_operation_and_enum():
    before = {
        "paths": {"/api/v1/cases": {"get": {}}},
        "components": {"schemas": {"State": {"enum": ["OPEN", "CLOSED"]}}},
    }
    after = {"paths": {}, "components": {"schemas": {"State": {"enum": ["OPEN"]}}}}
    assert len(breaking_changes(before, after)) == 2


def test_log_redaction_masks_credentials_and_contact_details():
    from darknetra.logging import redact_log

    value = redact_log(
        None,
        "info",
        {
            "event": "SYNTHETIC contact synthetic@example.test",
            "detail": {"password": "SYNTHETIC secret", "access_token": "SYNTHETIC bearer"},
        },
    )
    assert "synthetic@example.test" not in str(value)
    assert value["detail"] == {"password": "***", "access_token": "***"}
