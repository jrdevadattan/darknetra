from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import GlobalRole
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceDerivation,
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
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SHA512_PATTERN = re.compile(r"^[0-9a-f]{128}$")
_OBJECT_KEY_PATTERN = re.compile(r"^[!-~]+$")
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


def normalize_source_locator_for_dedup(locator: str) -> str:
    """Return trimmed exact Unicode text; do not URL-normalize or case-fold."""

    if not isinstance(locator, str):
        raise TypeError("source locator must be a string")
    normalized = locator.strip()
    if not normalized:
        raise ValueError("source locator must not be empty")
    return normalized


def sensitive_field_name(kind: EvidenceSensitiveValueKind) -> str:
    return kind.value.lower()


def canonical_sensitive_field_name(field_name: str) -> str:
    if not isinstance(field_name, str):
        raise TypeError("invalid sensitive field name")
    try:
        canonical = EvidenceSensitiveValueKind(field_name.upper()).value.lower()
    except (ValueError, AttributeError):
        raise ValueError("invalid sensitive field name") from None
    if field_name != canonical:
        raise ValueError("sensitive field name must use canonical lowercase spelling")
    return canonical


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
    value_id = uuid4()
    field_name = sensitive_field_name(kind)
    purpose = compose_sensitive_field_purpose(EVIDENCE_RESOURCE_TYPE, field_name)
    envelope = crypto.encrypt(plaintext, purpose=purpose, resource_id=str(value_id))
    packed = pack_envelope(envelope)
    blind_index = None
    if kind is EvidenceSensitiveValueKind.SOURCE_LOCATOR:
        normalized_locator = normalize_source_locator_for_dedup(plaintext)
        blind_index = crypto.blind_index(normalized_locator, purpose=purpose)
    return EvidenceSensitiveValue(
        id=value_id,
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


async def persist_sensitive_value(
    session: AsyncSession,
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
    """Mandatory owning write boundary for protected evidence values."""

    value = build_sensitive_value(
        case_id=case_id,
        evidence_id=evidence_id,
        kind=kind,
        plaintext=plaintext,
        crypto=crypto,
        contact_kind=contact_kind,
        wallet_network=wallet_network,
        wallet_asset=wallet_asset,
        policy_sensitive=policy_sensitive,
    )
    validate_sensitive_value_storage(value)
    session.add(value)
    await session.flush()
    return value


def preserve_evidence_manifest(
    artifact: EvidenceArtifact,
    *,
    media_type: str,
    size_bytes: int,
    sha256: str,
    object_key: str,
    sha512: str | None = None,
    ingested_at: datetime | None = None,
) -> None:
    """Set an artifact's authoritative preservation manifest exactly once."""

    if artifact.state is not EvidenceState.STAGING:
        raise EvidenceDigestImmutableError("evidence manifest has already been preserved")
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")
    if not isinstance(sha256, str) or not _SHA256_PATTERN.fullmatch(sha256):
        raise ValueError("sha256 must be canonical lowercase hexadecimal")
    if sha512 is not None and (
        not isinstance(sha512, str) or not _SHA512_PATTERN.fullmatch(sha512)
    ):
        raise ValueError("sha512 must be canonical lowercase hexadecimal when provided")
    if not isinstance(object_key, str) or not _OBJECT_KEY_PATTERN.fullmatch(object_key):
        raise ValueError("object_key must contain printable non-space ASCII only")
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

    envelope = unpack_envelope(value.envelope_mapping())
    purpose = compose_sensitive_field_purpose(
        EVIDENCE_RESOURCE_TYPE,
        sensitive_field_name(value.kind),
    )
    return rotate_sensitive_field(
        value=envelope,
        blind_index=value.blind_index,
        purpose=purpose,
        resource_id=str(value.id),
        keyring=keyring,
        rotate_blind_index=rotate_blind_index,
    )


def update_artifact_metadata(artifact: EvidenceArtifact, **changes: Any) -> None:
    """Apply mutable metadata without permitting manifest replacement."""

    unknown = set(changes) - set(EvidenceArtifact.__table__.columns.keys())
    if unknown:
        raise ValueError(f"unknown evidence fields: {', '.join(sorted(unknown))}")
    if (
        artifact.state != EvidenceState.STAGING
        and changes.get("state") == EvidenceState.STAGING
    ):
        raise EvidenceDigestImmutableError("preserved evidence cannot return to staging")
    for name, value in changes.items():
        if name in _IMMUTABLE_MANIFEST_FIELDS and artifact.state != EvidenceState.STAGING:
            raise EvidenceDigestImmutableError("preserved evidence manifest cannot be rewritten")
        setattr(artifact, name, value)


class EvidenceSensitiveValueProvider:
    """Read-only adapter for the shared audited reveal service."""

    def __init__(self, *, expected_evidence_id: UUID) -> None:
        self._expected_evidence_id = expected_evidence_id

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
            value_id = UUID(resource_id)
            canonical = canonical_sensitive_field_name(field_name)
            kind = EvidenceSensitiveValueKind(canonical.upper())
        except (TypeError, ValueError):
            return None
        row = await session.scalar(
            select(EvidenceSensitiveValue).where(
                EvidenceSensitiveValue.id == value_id,
                EvidenceSensitiveValue.evidence_id == self._expected_evidence_id,
                EvidenceSensitiveValue.case_id == case_id,
                EvidenceSensitiveValue.kind == kind,
            )
        )
        if row is None:
            return None
        envelope = unpack_envelope(row.envelope_mapping())
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
            canonical = canonical_sensitive_field_name(field_name)
            kind = EvidenceSensitiveValueKind(canonical.upper())
        except (TypeError, ValueError):
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


def validate_sensitive_value_storage(value: EvidenceSensitiveValue) -> None:
    unpack_envelope(value.envelope_mapping())
    if value.kind is EvidenceSensitiveValueKind.SOURCE_LOCATOR:
        if value.blind_index is None:
            raise ValueError("source locator requires a blind index")
    elif value.blind_index is not None:
        raise ValueError("this sensitive value kind does not permit a blind index")


def build_evidence_derivation(
    *,
    case_id: UUID,
    parent_evidence_id: UUID,
    child_evidence_id: UUID,
    transformation: str,
    transformer_version: str,
    parameters: dict[str, Any],
) -> EvidenceDerivation:
    from darknetra_api.services.provenance import derivation_parameters_digest

    return EvidenceDerivation(
        case_id=case_id,
        parent_evidence_id=parent_evidence_id,
        child_evidence_id=child_evidence_id,
        transformation=transformation,
        transformer_version=transformer_version,
        parameters_json=dict(parameters),
        parameters_digest=derivation_parameters_digest(parameters),
    )


__all__ = [
    "EVIDENCE_RESOURCE_TYPE",
    "EvidenceDigestImmutableError",
    "EvidenceSensitiveRevealPolicy",
    "EvidenceSensitiveValueProvider",
    "build_evidence_derivation",
    "build_sensitive_value",
    "canonical_sensitive_field_name",
    "normalize_source_locator_for_dedup",
    "persist_sensitive_value",
    "preserve_evidence_manifest",
    "rotate_evidence_sensitive_value",
    "sensitive_field_name",
    "update_artifact_metadata",
    "validate_sensitive_value_storage",
]
