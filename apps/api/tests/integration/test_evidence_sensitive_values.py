from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import sqlalchemy as sa
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.custody import CustodyEvent
from darknetra_api.models.enums import CaseSensitivity, CaseStatus, GlobalRole
from darknetra_api.models.evidence import (
    EvidenceArtifact,
    EvidenceDerivation,
    EvidenceSensitiveValue,
    EvidenceSensitiveValueKind,
    EvidenceSourceClass,
    EvidenceState,
)
from darknetra_api.models.job import AnalysisJob
from darknetra_api.models.user import User
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.services.evidence import (
    EvidenceSensitiveRevealPolicy,
    EvidenceSensitiveValueProvider,
    build_sensitive_value,
)
from darknetra_api.services.sensitive_values import (
    bind_sensitive_reveal_context,
    reveal_sensitive_value,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def crypto() -> SensitiveFieldCrypto:
    return SensitiveFieldCrypto(
        field_keys={"v1": secrets.token_bytes(32)},
        active_key_version="v1",
        blind_index_key=secrets.token_bytes(32),
    )


def user(username: str, role: GlobalRole) -> User:
    return User(
        username=username,
        username_normalized=username.casefold(),
        display_name=username,
        password_hash="not-used",
        global_roles=[role],
        is_active=True,
        must_change_password=False,
    )


async def clear_state() -> None:
    async with async_session_factory() as session:
        for model in (
            CustodyEvent,
            EvidenceDerivation,
            EvidenceSensitiveValue,
            EvidenceArtifact,
            AnalysisJob,
            AuditEvent,
            CaseMembershipRole,
            CaseMembership,
            Case,
            AuthSession,
            User,
        ):
            await session.execute(sa.delete(model))
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_database() -> None:
    await clear_state()
    yield
    await clear_state()


async def add_membership(session, case: Case, actor: User, role: GlobalRole) -> None:
    membership = CaseMembership(case_id=case.id, user_id=actor.id)
    session.add(membership)
    await session.flush()
    session.add(CaseMembershipRole(membership_id=membership.id, role=role))


def artifact(case: Case, collector: User) -> EvidenceArtifact:
    return EvidenceArtifact(
        case_id=case.id,
        source_class=EvidenceSourceClass.SYNTHETIC,
        source_type="web-capture",
        acquisition_method="authorized-fixture",
        collector_user_id=collector.id,
        captured_at=datetime.now(UTC),
        ingested_at=datetime.now(UTC),
        media_type="text/html",
        size_bytes=10,
        sha256="a" * 64,
        sha512="b" * 128,
        object_key="sha256/aa/" + "a" * 64,
        state=EvidenceState.PRESERVED,
        policy_restricted=True,
        allow_original_download=False,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_write_pack_persist_load_unpack_and_audited_reveal_share_context() -> None:
    crypto_service = crypto()
    plaintext = "https://private.example/path"
    async with async_session_factory() as session:
        owner = user("evidence-owner", GlobalRole.CASE_OWNER)
        viewer = user("evidence-viewer", GlobalRole.VIEWER)
        session.add_all([owner, viewer])
        await session.flush()
        case = Case(
            case_code="EVIDENCE-ROUNDTRIP",
            title="Evidence round trip",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.flush()
        await add_membership(session, case, owner, GlobalRole.CASE_OWNER)
        await add_membership(session, case, viewer, GlobalRole.VIEWER)
        stored_artifact = artifact(case, owner)
        session.add(stored_artifact)
        await session.flush()
        protected = build_sensitive_value(
            case_id=case.id,
            evidence_id=stored_artifact.id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext=plaintext,
            crypto=crypto_service,
        )
        session.add(protected)
        await session.commit()

        loaded = await session.scalar(
            select(EvidenceSensitiveValue).where(EvidenceSensitiveValue.id == protected.id)
        )
        assert loaded is not None
        assert loaded.key_version and loaded.nonce_b64 and loaded.ciphertext_b64
        assert loaded.blind_index is not None

        bind_sensitive_reveal_context(
            session,
            provider=EvidenceSensitiveValueProvider(),
            permission_predicate=EvidenceSensitiveRevealPolicy(),
            crypto=crypto_service,
            request_id="evidence-roundtrip-request",
        )
        with pytest.raises(AuthorizationDenied):
            await reveal_sensitive_value(
                actor=viewer,
                case_id=case.id,
                resource_type="evidence",
                resource_id=str(stored_artifact.id),
                field_name="source_locator",
                reason="Viewer may not reveal protected values",
                session=session,
            )

        revealed = await reveal_sensitive_value(
            actor=owner,
            case_id=case.id,
            resource_type="evidence",
            resource_id=str(stored_artifact.id),
            field_name="source_locator",
            reason="Validate the original source location",
            session=session,
        )
        assert revealed == plaintext
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "SENSITIVE_VALUE_REVEALED")
        )
        assert event is not None
        assert plaintext not in repr(event.metadata_json)

        with pytest.raises(CaseNotFound) as unknown:
            await reveal_sensitive_value(
                actor=owner,
                case_id=case.id,
                resource_type="evidence",
                resource_id=str(uuid4()),
                field_name="source_locator",
                reason="Unknown values must remain indistinguishable",
                session=session,
            )
        with pytest.raises(CaseNotFound) as cross_case:
            await reveal_sensitive_value(
                actor=owner,
                case_id=uuid4(),
                resource_type="evidence",
                resource_id=str(stored_artifact.id),
                field_name="source_locator",
                reason="Cross case values must remain indistinguishable",
                session=session,
            )
        assert unknown.value.args == cross_case.value.args == ("resource not found",)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_evidence_ids_lineage_case_scope_and_custody_are_enforced() -> None:
    async with async_session_factory() as session:
        owner = user("constraint-owner", GlobalRole.CASE_OWNER)
        session.add(owner)
        await session.flush()
        cases = [
            Case(
                case_code=f"EVIDENCE-SCOPE-{number}",
                title=f"Scope case {number}",
                status=CaseStatus.OPEN,
                sensitivity=CaseSensitivity.STANDARD,
                owner_user_id=owner.id,
                source_authority_summary="Synthetic authorized fixture",
            )
            for number in (1, 2)
        ]
        session.add_all(cases)
        await session.flush()
        artifacts = [artifact(case, owner) for case in cases]
        child = artifact(cases[0], owner)
        session.add_all([*artifacts, child])
        await session.commit()

        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    sa.insert(EvidenceArtifact).values(
                        id=artifacts[0].id,
                        case_id=cases[0].id,
                        source_class=EvidenceSourceClass.SYNTHETIC,
                        source_type="duplicate",
                        acquisition_method="invalid-duplicate",
                        collector_user_id=owner.id,
                        captured_at=datetime.now(UTC),
                        state=EvidenceState.STAGING,
                    )
                )

        wrong_case_value = build_sensitive_value(
            case_id=cases[1].id,
            evidence_id=artifacts[0].id,
            kind=EvidenceSensitiveValueKind.AUTHORITY_REFERENCE,
            plaintext="authority belongs to another case",
            crypto=crypto(),
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(wrong_case_value)
                await session.flush()

        lineage = EvidenceDerivation(
            case_id=cases[0].id,
            parent_evidence_id=artifacts[0].id,
            child_evidence_id=child.id,
            transformation="extract",
            transformer_version="1",
            parameters_json={"member": "safe.txt"},
        )
        session.add(lineage)
        await session.commit()

        cross_case_lineage = EvidenceDerivation(
            case_id=cases[0].id,
            parent_evidence_id=artifacts[0].id,
            child_evidence_id=artifacts[1].id,
            transformation="invalid-cross-case",
            transformer_version="1",
            parameters_json={},
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(cross_case_lineage)
                await session.flush()

        custody = CustodyEvent(
            case_id=cases[0].id,
            evidence_id=artifacts[0].id,
            actor_user_id=owner.id,
            action="PRESERVED",
            request_id="custody-append-only",
            integrity_sha256="a" * 64,
            metadata_json={"location": "vault"},
        )
        session.add(custody)
        await session.commit()
        custody.action = "MUTATED"
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()
