import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_published_evidence_revisions_are_immutable() -> None:
    expected_sha256 = {
        "b7c19a4e5d20_enforce_evidence_invariants.py": (
            "ae06ff9fb0163fe70685d0fd3918b2ea354efae8187d10de3a3d7eb727c4d688"
        ),
        "c3f80a92d614_harden_evidence_lifecycle.py": (
            "483e0aaef171e13167d0587c496b04bd2da511392abbf0e0241135b1019336eb"
        ),
    }
    versions = ROOT / "apps" / "api" / "alembic" / "versions"

    for filename, expected in expected_sha256.items():
        checkout_bytes = (versions / filename).read_bytes()
        git_blob_content = checkout_bytes.replace(b"\r\n", b"\n")
        assert hashlib.sha256(git_blob_content).hexdigest() == expected


def test_final_evidence_transition_is_a_new_child_of_published_c3() -> None:
    migration = (
        ROOT
        / "apps"
        / "api"
        / "alembic"
        / "versions"
        / "d4e91b7a2c08_finalize_evidence_transitions.py"
    )
    content = migration.read_text(encoding="utf-8")
    assert 'revision: str = "d4e91b7a2c08"' in content
    assert 'down_revision: str | Sequence[str] | None = "c3f80a92d614"' in content
