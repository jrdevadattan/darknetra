from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import darknetra_api.services.evidence as evidence_service
import pytest
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceSensitiveValue,
    EvidenceSensitiveValueKind,
    EvidenceSourceClass,
    EvidenceState,
)
from darknetra_api.schemas.evidence import (
    EvidenceArtifactResponse,
    EvidenceSensitiveValueSummary,
)
from darknetra_api.security.encrypted_fields import unpack_envelope
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.security.keyring import SensitiveFieldKeyring
from darknetra_api.security.purposes import compose_sensitive_field_purpose
from darknetra_api.services.evidence import (
    EvidenceDigestImmutableError,
    build_sensitive_value,
    normalize_source_locator_for_dedup,
    preserve_evidence_manifest,
    rotate_evidence_sensitive_value,
    update_artifact_metadata,
)
from darknetra_api.services.provenance import (
    canonical_derivation_parameters_json,
    derivation_parameters_digest,
)


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": secrets.token_bytes(32)},
        active_key_version="v1",
        blind_index_key=secrets.token_bytes(32),
    )


def test_public_purpose_composer_preserves_component_boundaries() -> None:
    assert compose_sensitive_field_purpose("evidence.source", "locator") != (
        compose_sensitive_field_purpose("evidence", "source.locator")
    )


def test_locator_dedup_is_trimmed_exact_unicode_equality() -> None:
    assert normalize_source_locator_for_dedup("  HTTPS://Example.test/Path  ") == (
        "HTTPS://Example.test/Path"
    )
    assert normalize_source_locator_for_dedup("HTTPS://Example.test/Path") != (
        normalize_source_locator_for_dedup("https://example.test/Path")
    )
    assert normalize_source_locator_for_dedup("https://example.test/Path") != (
        normalize_source_locator_for_dedup("https://example.test/path")
    )
    with pytest.raises(ValueError, match="empty"):
        normalize_source_locator_for_dedup(" \t\n ")


def test_derivation_parameters_use_versioned_canonical_json() -> None:
    first = {"z": [1, True], "a": {"é": "value"}}
    reordered = {"a": {"é": "value"}, "z": [1, True]}
    assert canonical_derivation_parameters_json(first) == (
        canonical_derivation_parameters_json(reordered)
    )
    assert derivation_parameters_digest(first) == derivation_parameters_digest(reordered)
    assert derivation_parameters_digest(first) != derivation_parameters_digest({"z": [1]})
    with pytest.raises(ValueError, match="finite"):
        canonical_derivation_parameters_json({"bad": float("nan")})


def test_derivation_parameters_normalize_only_integer_valued_numbers() -> None:
    parameters = {
        "positive_exponent": 1e20,
        "integral_float": 1.0,
        "negative_zero": -0.0,
        "large_integer": 123456789012345678901234567890,
        "nested": [2.0, {"value": -3.0}],
    }

    assert canonical_derivation_parameters_json(parameters) == (
        b'{"integral_float":1,"large_integer":123456789012345678901234567890,'
        b'"negative_zero":0,"nested":[2,{"value":-3}],'
        b'"positive_exponent":100000000000000000000}'
    )

    assert canonical_derivation_parameters_json(
        {
            "negative_exponent": -1e23,
            "nested": [1e30, {"positive_exponent": 1e23}],
        }
    ) == (
        b'{"negative_exponent":-100000000000000000000000,'
        b'"nested":[1000000000000000000000000000000,'
        b'{"positive_exponent":100000000000000000000000}]}'
    )

    for unsupported in (1e-7, 1.5, float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="integer-valued"):
            canonical_derivation_parameters_json({"unsupported": unsupported})
    for unsupported_type in (Decimal(1), 1 + 0j):
        with pytest.raises(ValueError, match="supported JSON"):
            canonical_derivation_parameters_json({"unsupported": unsupported_type})


def test_repeated_values_use_independent_row_identity_for_aad() -> None:
    evidence_id = uuid4()
    crypto_service = crypto()
    first = build_sensitive_value(
        case_id=uuid4(),
        evidence_id=evidence_id,
        kind=EvidenceSensitiveValueKind.CUSTODY_NOTE,
        plaintext="first custody note",
        crypto=crypto_service,
    )
    second = build_sensitive_value(
        case_id=first.case_id,
        evidence_id=evidence_id,
        kind=EvidenceSensitiveValueKind.CUSTODY_NOTE,
        plaintext="second custody note",
        crypto=crypto_service,
    )
    purpose = compose_sensitive_field_purpose("evidence", "custody_note")
    first_envelope = unpack_envelope(first.envelope_mapping())
    second_envelope = unpack_envelope(second.envelope_mapping())
    assert first.id != second.id
    assert crypto_service.decrypt(first_envelope, purpose=purpose, resource_id=str(first.id)) == (
        "first custody note"
    )
    assert crypto_service.decrypt(second_envelope, purpose=purpose, resource_id=str(second.id)) == (
        "second custody note"
    )


@pytest.mark.parametrize(
    ("kind", "plaintext", "expects_index"),
    [
        (EvidenceSensitiveValueKind.SOURCE_LOCATOR, "HTTPS://Example.test/path", True),
        (EvidenceSensitiveValueKind.AUTHORITY_REFERENCE, "warrant-42", False),
        (EvidenceSensitiveValueKind.PROTECTED_NOTE, "analyst rationale", False),
        (EvidenceSensitiveValueKind.CUSTODY_NOTE, "sealed by collector", False),
        (EvidenceSensitiveValueKind.CONTACT, "private@example.test", False),
        (EvidenceSensitiveValueKind.POLICY_RESTRICTED_WALLET, "0xabc", False),
    ],
)
def test_sensitive_value_writer_persists_complete_envelope_and_only_documented_index(
    kind: EvidenceSensitiveValueKind,
    plaintext: str,
    expects_index: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case_id = uuid4()
    evidence_id = uuid4()
    crypto_service = crypto()
    composer_calls: list[tuple[str, str]] = []
    pack_calls = []
    real_composer = compose_sensitive_field_purpose
    real_pack = evidence_service.pack_envelope

    def tracked_composer(resource_type: str, field_name: str) -> str:
        composer_calls.append((resource_type, field_name))
        return real_composer(resource_type, field_name)

    def tracked_pack(envelope):
        pack_calls.append(envelope)
        return real_pack(envelope)

    monkeypatch.setattr(evidence_service, "compose_sensitive_field_purpose", tracked_composer)
    monkeypatch.setattr(evidence_service, "pack_envelope", tracked_pack)
    value = build_sensitive_value(
        case_id=case_id,
        evidence_id=evidence_id,
        kind=kind,
        plaintext=plaintext,
        crypto=crypto_service,
    )

    envelope = unpack_envelope(
        {
            "key_version": value.key_version,
            "nonce_b64": value.nonce_b64,
            "ciphertext_b64": value.ciphertext_b64,
        }
    )
    purpose = compose_sensitive_field_purpose("evidence", kind.value.lower())
    assert crypto_service.decrypt(envelope, purpose=purpose, resource_id=str(value.id)) == plaintext
    assert composer_calls == [("evidence", kind.value.lower())]
    assert len(pack_calls) == 1
    assert (value.blind_index is not None) is expects_index

    rendered = repr(value)
    assert plaintext not in rendered
    assert value.key_version not in rendered
    assert value.nonce_b64 not in rendered
    assert value.ciphertext_b64 not in rendered
    if value.blind_index is not None:
        assert value.blind_index not in rendered


def test_artifact_digest_fields_become_immutable_after_preservation() -> None:
    artifact = EvidenceArtifact(
        case_id=uuid4(),
        source_class=EvidenceSourceClass.PUBLIC_OBSERVATION,
        source_type="website",
        acquisition_method="authorized-download",
        collector_user_id=uuid4(),
        captured_at=datetime.now(UTC),
        ingested_at=datetime.now(UTC),
        media_type="text/html",
        size_bytes=12,
        sha256="a" * 64,
        sha512="b" * 128,
        object_key="sha256/aa/" + "a" * 64,
        state=EvidenceState.PRESERVED,
        policy_restricted=False,
        allow_original_download=False,
    )

    with pytest.raises(EvidenceDigestImmutableError):
        update_artifact_metadata(artifact, sha256="c" * 64)

    with pytest.raises(EvidenceDigestImmutableError, match="cannot return to staging"):
        update_artifact_metadata(artifact, state=EvidenceState.STAGING)


def test_preservation_accepts_sha256_only_and_validates_optional_sha512() -> None:
    artifact = EvidenceArtifact(
        case_id=uuid4(),
        source_class=EvidenceSourceClass.AUTHORIZED_IMPORT,
        source_type="document",
        acquisition_method="upload",
        collector_user_id=uuid4(),
        captured_at=datetime.now(UTC),
        state=EvidenceState.STAGING,
    )

    preserve_evidence_manifest(
        artifact,
        media_type="application/octet-stream",
        size_bytes=0,
        sha256="a" * 64,
        object_key="sha256/aa/" + "a" * 64,
    )

    assert artifact.state is EvidenceState.PRESERVED
    assert artifact.sha512 is None

    invalid_sha512 = EvidenceArtifact(
        case_id=uuid4(),
        source_class=EvidenceSourceClass.AUTHORIZED_IMPORT,
        source_type="document",
        acquisition_method="upload",
        collector_user_id=uuid4(),
        captured_at=datetime.now(UTC),
        state=EvidenceState.STAGING,
    )
    with pytest.raises(ValueError, match="sha512"):
        preserve_evidence_manifest(
            invalid_sha512,
            media_type="application/octet-stream",
            size_bytes=1,
            sha256="b" * 64,
            sha512="not-canonical",
            object_key="sha256/bb/" + "b" * 64,
        )


@pytest.mark.parametrize(
    ("sha256", "object_key", "message"),
    [
        ("A" * 64, "sha256/aa/value", "sha256"),
        ("a" * 64, "   ", "object_key"),
        ("a" * 64, "\t", "object_key"),
        ("a" * 64, "\n", "object_key"),
        ("a" * 64, "\u00a0", "object_key"),
        ("a" * 64, "sha256/path with-space", "object_key"),
    ],
)
def test_preservation_rejects_noncanonical_required_manifest_fields(
    sha256: str,
    object_key: str,
    message: str,
) -> None:
    artifact = EvidenceArtifact(
        case_id=uuid4(),
        source_class=EvidenceSourceClass.AUTHORIZED_IMPORT,
        source_type="document",
        acquisition_method="upload",
        collector_user_id=uuid4(),
        captured_at=datetime.now(UTC),
        state=EvidenceState.STAGING,
    )

    with pytest.raises(ValueError, match=message):
        preserve_evidence_manifest(
            artifact,
            media_type="application/octet-stream",
            size_bytes=1,
            sha256=sha256,
            object_key=object_key,
        )


def test_evidence_rotation_reuses_canonical_purpose_and_value_id() -> None:
    case_id = uuid4()
    evidence_id = uuid4()
    old_key = secrets.token_bytes(32)
    blind_index_key = secrets.token_bytes(32)
    old_crypto = SensitiveFieldCrypto(
        field_keys={"v1": old_key},
        active_key_version="v1",
        blind_index_key=blind_index_key,
    )
    value = build_sensitive_value(
        case_id=case_id,
        evidence_id=evidence_id,
        kind=EvidenceSensitiveValueKind.CUSTODY_NOTE,
        plaintext="rotation stays in the owning context",
        crypto=old_crypto,
    )
    keyring = SensitiveFieldKeyring(
        keys={"v1": old_key, "v2": secrets.token_bytes(32)},
        active_version="v2",
        blind_index_key=blind_index_key,
    )

    rotated = rotate_evidence_sensitive_value(value, keyring=keyring)
    purpose = compose_sensitive_field_purpose("evidence", "custody_note")
    assert keyring.crypto().decrypt(
        rotated.value,
        purpose=purpose,
        resource_id=str(value.id),
    ) == "rotation stays in the owning context"


def test_ordinary_artifact_and_sensitive_repr_omit_storage_secrets() -> None:
    artifact = EvidenceArtifact(
        case_id=uuid4(),
        source_class=EvidenceSourceClass.AUTHORIZED_IMPORT,
        source_type="document",
        acquisition_method="upload",
        collector_user_id=uuid4(),
        captured_at=datetime.now(UTC),
        ingested_at=datetime.now(UTC),
        media_type="application/pdf",
        size_bytes=1,
        sha256="a" * 64,
        sha512="b" * 128,
        object_key="sha256/aa/" + "a" * 64,
        state=EvidenceState.PRESERVED,
        policy_restricted=False,
        allow_original_download=False,
    )
    artifact.id = uuid4()
    artifact.created_at = datetime.now(UTC)
    artifact.updated_at = datetime.now(UTC)
    artifact_response = EvidenceArtifactResponse.model_validate(artifact).model_dump()
    assert "object_key" not in artifact_response

    sensitive = build_sensitive_value(
        case_id=artifact.case_id,
        evidence_id=artifact.id,
        kind=EvidenceSensitiveValueKind.PROTECTED_NOTE,
        plaintext="schema must not leak this",
        crypto=crypto(),
    )
    sensitive.created_at = datetime.now(UTC)
    sensitive_response = EvidenceSensitiveValueSummary.model_validate(sensitive).model_dump()
    assert not {
        "key_version",
        "nonce_b64",
        "ciphertext_b64",
        "blind_index",
    }.intersection(sensitive_response)

    assert "ciphertext" not in EvidenceSensitiveValue.__table__.columns
    assert EvidenceSensitiveValue.__table__.columns.blind_index.nullable is True
