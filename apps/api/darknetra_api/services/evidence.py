from __future__ import annotations

from datetime import UTC, datetime

from darknetra_api.models.evidence import EvidenceArtifact, EvidenceState


class EvidenceDigestImmutableError(ValueError):
    """A preserved evidence manifest or expected digest was rewritten."""


def preserve_evidence_manifest(
    artifact: EvidenceArtifact,
    *,
    media_type: str,
    size_bytes: int,
    sha256: str,
    sha512: str | None,
    object_key: str,
    ingested_at: datetime | None = None,
) -> None:
    """Set the authoritative preservation manifest exactly once."""

    if artifact.state is not EvidenceState.STAGING or artifact.sha256 is not None or artifact.object_key is not None:
        raise EvidenceDigestImmutableError("evidence manifest has already been preserved")
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")

    artifact.media_type = media_type
    artifact.size_bytes = size_bytes
    artifact.sha256 = sha256
    artifact.sha512 = sha512
    artifact.object_key = object_key
    artifact.ingested_at = ingested_at or datetime.now(UTC)
    artifact.state = EvidenceState.PRESERVED
