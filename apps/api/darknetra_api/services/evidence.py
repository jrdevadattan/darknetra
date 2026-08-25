from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceSensitiveValue,
    EvidenceSensitiveValueKind,
    EvidenceState,
)
from darknetra_api.security.encrypted_fields import pack_envelope, unpack_envelope
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.security.keyring import (
    SensitiveFieldKeyring,
    SensitiveFieldRotationResult,
    rotate_sensitive_field,
)
from darknetra_api.security.purposes import compose_sensitive_field_purpose
from darknetra_api.services.sensitive_values import SensitiveValue

EVIDENCE_RESOURCE_TYPE = "evidence"
_IMMUTABLE_MANIFEST_FIELDS = frozenset({"size_bytes", "sha256", "sha512", "object_key"})
_FIELD_REVEAL_ROLES = {
    EvidenceSensitiveValueKind.SOURCE_LOCATOR: frozenset(
        {GlobalRole.CASE_OWNER, GlobalRole.COLLECTOR, GlobalRole.ANALYST, GlobalRole.REVIEWER}
    ),
    EvidenceSensitiveValueKind.AUTHORITY_REFERENCE: frozenset(
        {GlobalRole.CASE_OWNER, GlobalRole.REVIEWER, GlobalRole.AUDITOR}
    ),
    EvidenceSensitiveValueKind.PROTECTED_NOTE: frozenset(
        {GlobalRole.CASE_OWNER, GlobalRole.ANALYST, GlobalRole.REVIEWER}
    ),
    EvidenceSensitiveValueKind.CUSTODY_NOTE: frozenset(
        {GlobalRole.CASE_OWNER, GlobalRole.COLLECTOR, GlobalRole.REVIEWER, GlobalRole.AUDITOR}
    ),
    EvidenceSensitiveValueKind.CONTACT: frozenset(
        {GlobalRole.CASE_OWNER, GlobalRole.COLLECTOR, GlobalRole.ANALYST, GlobalRole.REVIEWER}
    ),
    EvidenceSensitiveValueKind.POLICY_RESTRICTED_WALLET: frozenset(
        {GlobalRole.CASE_OWNER, GlobalRole.REVIEWER}
    ),
}


class EvidenceDigestImmutableError(ValueError):
    """A preserved evidence manifest or expected digest was rewritten."""


def sensitive_field_name(kind: EvidenceSensitiveValueKind) -> str:
    return kind.value.lower()


def build_sensitive_value(
    *,
    case_id: UUID,
    evidence_id: UUID,
    kind: EvidenceSensitiveValueKind,
    plaintext: str,
    crypto: SensitiveFieldCrypto,
    contact_kind: str | None = None,
    wallet_network: str | None = None,
    wallet_asset: str | None = None,
    policy_sensitive: bool = True,
) -> EvidenceSensitiveValue:
    """Encrypt one protected evidence field and return a persistence-ready row."""

    if not isinstance(plaintext, str) or not plaintext:
        raise ValueError("sensitive value plaintext must be non-empty")
    field_name = sensitive_field_name(kind)
    purpose = compose_sensitive_field_purpose(EVIDENCE_RESOURCE_TYPE, field_name)
    envelope = crypto.encrypt(plaintext, purpose=purpose, resource_id=str(evidence_id))
    packed = pack_envelope(envelope)
    blind_index = None
    if kind is EvidenceSensitiveValueKind.SOURCE_LOCATOR:
        normalized_locator = plaintext.strip()
        blind_index = crypto.blind_index(normalized_locator, purpose=purpose)
    return EvidenceSensitiveValue(
        id=uuid4(),
        case_id=case_id,
        evidence_id=evidence_id,
        kind=kind,
        key_version=packed["key_version"],
        nonce_b64=packed["nonce_b64"],
        ciphertext_b64=packed["ciphertext_b64"],
        blind_index=blind_index,
        contact_kind=contact_kind,
        wallet_network=wallet_network,
        wallet_asset=wallet_asset,
        policy_sensitive=policy_sensitive,
    )


def preserve_evidence_manifest(
    artifact: EvidenceArtifact,
    *,
    media_type: str,
    size_bytes: int,
    sha256: str,
    sha512: str,
    object_key: str,
    ingested_at: datetime | None = None,
) -> None:
    """Set an artifact's authoritative preservation manifest exactly once."""

    if artifact.state is not EvidenceState.STAGING or any(
        getattr(artifact, field) is not None for field in _IMMUTABLE_MANIFEST_FIELDS
    ):
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


def rotate_evidence_sensitive_value(
    value: EvidenceSensitiveValue,
    *,
    keyring: SensitiveFieldKeyring,
    rotate_blind_index: bool = False,
) -> SensitiveFieldRotationResult:
    """Rotate one stored evidence value with the same purpose used by write/reveal."""

    envelope = unpack_envelope(
        {
            "key_version": value.key_version,
            "nonce_b64": value.nonce_b64,
            "ciphertext_b64": value.ciphertext_b64,
        }
    )
    purpose = compose_sensitive_field_purpose(
        EVIDENCE_RESOURCE_TYPE,
        sensitive_field_name(value.kind),
    )
    return rotate_sensitive_field(
        value=envelope,
        blind_index=value.blind_index,
        purpose=purpose,
        resource_id=str(value.evidence_id),
        keyring=keyring,
        rotate_blind_index=rotate_blind_index,
    )


def update_artifact_metadata(artifact: EvidenceArtifact, **changes: Any) -> None:
    """Apply mutable metadata without permitting manifest replacement."""

    unknown = set(changes) - set(EvidenceArtifact.__table__.columns.keys())
    if unknown:
        raise ValueError(f"unknown evidence fields: {', '.join(sorted(unknown))}")
    for name, value in changes.items():
        if name in _IMMUTABLE_MANIFEST_FIELDS and getattr(artifact, name) is not None:
            raise EvidenceDigestImmutableError("preserved evidence manifest cannot be rewritten")
        setattr(artifact, name, value)


class EvidenceSensitiveValueProvider:
    """Read-only adapter for the shared audited reveal service."""

    async def __call__(
        self,
        *,
        case_id: UUID,
        resource_type: str,
        resource_id: str,
        field_name: str,
        session: AsyncSession,
    ) -> SensitiveValue | None:
        if resource_type != EVIDENCE_RESOURCE_TYPE:
            return None
        try:
            evidence_id = UUID(resource_id)
            kind = EvidenceSensitiveValueKind(field_name.upper())
        except (ValueError, AttributeError):
            return None
        row = await session.scalar(
            select(EvidenceSensitiveValue).where(
                EvidenceSensitiveValue.evidence_id == evidence_id,
                EvidenceSensitiveValue.case_id == case_id,
                EvidenceSensitiveValue.kind == kind,
            )
        )
        if row is None:
            return None
        envelope = unpack_envelope(
            {
                "key_version": row.key_version,
                "nonce_b64": row.nonce_b64,
                "ciphertext_b64": row.ciphertext_b64,
            }
        )
        return SensitiveValue(envelope=envelope)


class EvidenceSensitiveRevealPolicy:
    """Read-only field policy; case-role enforcement remains in the shared service."""

    async def __call__(
        self,
        *,
        actor: Any,
        case_id: UUID,
        resource_type: str,
        resource_id: str,
        field_name: str,
        session: AsyncSession,
    ) -> bool:
        del resource_id
        if resource_type != EVIDENCE_RESOURCE_TYPE:
            return False
        try:
            kind = EvidenceSensitiveValueKind(field_name.upper())
        except (ValueError, AttributeError):
            return False
        membership_id = await session.scalar(
            select(CaseMembership.id).where(
                CaseMembership.case_id == case_id,
                CaseMembership.user_id == actor.id,
            )
        )
        if membership_id is None:
            return False
        persisted_roles = set(
            (
                await session.scalars(
                    select(CaseMembershipRole.role).where(
                        CaseMembershipRole.membership_id == membership_id
                    )
                )
            ).all()
        )
        effective_roles = persisted_roles.intersection(set(actor.global_roles))
        return bool(effective_roles.intersection(_FIELD_REVEAL_ROLES[kind]))


__all__ = [
    "EVIDENCE_RESOURCE_TYPE",
    "EvidenceDigestImmutableError",
    "EvidenceSensitiveRevealPolicy",
    "EvidenceSensitiveValueProvider",
    "build_sensitive_value",
    "preserve_evidence_manifest",
    "rotate_evidence_sensitive_value",
    "sensitive_field_name",
    "update_artifact_metadata",
]
