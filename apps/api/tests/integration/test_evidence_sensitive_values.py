from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from darknetra_api.authz.policy import AuthorizationDenied, CaseNotFound
from darknetra_api.config import get_settings
from darknetra_api.db.session import async_session_factory, get_db_session
from darknetra_api.main import app
from darknetra_api.models.audit import AuditEvent
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
from darknetra_api.models.user import User
from darknetra_api.security.encryption import SensitiveFieldCrypto
from darknetra_api.security.passwords import hash_password
from darknetra_api.services.evidence import (
    EvidenceSensitiveRevealPolicy,
    EvidenceSensitiveValueProvider,
    build_evidence_derivation,
    build_sensitive_value,
    persist_sensitive_value,
    preserve_evidence_manifest,
    update_artifact_metadata,
)
from darknetra_api.services.provenance import derivation_parameters_digest
from darknetra_api.services.sensitive_values import (
    bind_sensitive_reveal_context,
    reveal_sensitive_value,
)
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@app.get("/api/v1/test-only-unrelated-failure", include_in_schema=False)
async def _test_only_unrelated_failure_route() -> None:
    raise RuntimeError("unrelated synthetic failure")


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
    settings = get_settings()
    owner_url = settings.database_owner_url or settings.database_url
    owner_engine = create_async_engine(owner_url)
    owner_sessions = async_sessionmaker(owner_engine, expire_on_commit=False)
    async with owner_sessions() as session:
        await session.execute(
            sa.text(
                "TRUNCATE custody_events, evidence_derivations, evidence_sensitive_values, "
                "evidence_artifacts, jobs, audit_events, case_membership_roles, "
                "case_memberships, cases, auth_sessions, users CASCADE"
            )
        )
        await session.commit()
    await owner_engine.dispose()


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
        other_case = Case(
            case_code="EVIDENCE-OTHER-CASE",
            title="Other existing case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add_all([case, other_case])
        await session.flush()
        await add_membership(session, case, owner, GlobalRole.CASE_OWNER)
        await add_membership(session, case, viewer, GlobalRole.VIEWER)
        await add_membership(session, other_case, owner, GlobalRole.CASE_OWNER)
        stored_artifact = artifact(case, owner)
        other_artifact = artifact(other_case, owner)
        session.add_all([stored_artifact, other_artifact])
        await session.flush()
        protected = await persist_sensitive_value(
            session,
            case_id=case.id,
            evidence_id=stored_artifact.id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext=plaintext,
            crypto=crypto_service,
        )
        other_value = await persist_sensitive_value(
            session,
            case_id=other_case.id,
            evidence_id=other_artifact.id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext="https://other-case.example/path",
            crypto=crypto_service,
        )
        repeated_values = []
        for kind in (
            EvidenceSensitiveValueKind.CUSTODY_NOTE,
            EvidenceSensitiveValueKind.CONTACT,
            EvidenceSensitiveValueKind.POLICY_RESTRICTED_WALLET,
            EvidenceSensitiveValueKind.PROTECTED_NOTE,
        ):
            for number in (1, 2):
                repeated_plaintext = f"{kind.value.lower()} value {number}"
                repeated_values.append(
                    (
                        await persist_sensitive_value(
                            session,
                            case_id=case.id,
                            evidence_id=stored_artifact.id,
                            kind=kind,
                            plaintext=repeated_plaintext,
                            crypto=crypto_service,
                        ),
                        repeated_plaintext,
                    )
                )
        await session.commit()

        loaded = await session.scalar(
            select(EvidenceSensitiveValue).where(EvidenceSensitiveValue.id == protected.id)
        )
        assert loaded is not None
        assert loaded.key_version and loaded.nonce_b64 and loaded.ciphertext_b64
        assert loaded.blind_index is not None

        bind_sensitive_reveal_context(
            session,
            provider=EvidenceSensitiveValueProvider(expected_evidence_id=stored_artifact.id),
            permission_predicate=EvidenceSensitiveRevealPolicy(),
            crypto=crypto_service,
            request_id="evidence-roundtrip-request",
        )
        with pytest.raises(AuthorizationDenied):
            await reveal_sensitive_value(
                actor=viewer,
                case_id=case.id,
                resource_type="evidence",
                resource_id=str(protected.id),
                field_name="source_locator",
                reason="Viewer may not reveal protected values",
                session=session,
            )

        revealed = await reveal_sensitive_value(
            actor=owner,
            case_id=case.id,
            resource_type="evidence",
            resource_id=str(protected.id),
            field_name="source_locator",
            reason="Validate the original source location",
            session=session,
        )
        assert revealed == plaintext
        for value, expected in repeated_values:
            revealed_repeated = await reveal_sensitive_value(
                actor=owner,
                case_id=case.id,
                resource_type="evidence",
                resource_id=str(value.id),
                field_name=value.kind.value.lower(),
                reason="Prove repeated protected values remain isolated",
                session=session,
            )
            assert revealed_repeated == expected
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
                case_id=case.id,
                resource_type="evidence",
                resource_id=str(other_value.id),
                field_name="source_locator",
                reason="Cross case values must remain indistinguishable",
                session=session,
            )
        assert unknown.value.args == cross_case.value.args == ("resource not found",)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_asgi_reveal_enforces_auth_csrf_canonical_field_and_no_store() -> None:
    crypto_service = crypto()
    password = "Evidence route password 42"
    async with async_session_factory() as session:
        owner = user("evidence-route-owner", GlobalRole.CASE_OWNER)
        owner.password_hash = hash_password(password)
        session.add(owner)
        await session.flush()
        case = Case(
            case_code="EVIDENCE-ASGI",
            title="ASGI reveal boundary",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        other_case = Case(
            case_code="EVIDENCE-ASGI-OTHER",
            title="Other ASGI reveal boundary",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.RESTRICTED,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add_all([case, other_case])
        await session.flush()
        await add_membership(session, case, owner, GlobalRole.CASE_OWNER)
        await add_membership(session, other_case, owner, GlobalRole.CASE_OWNER)
        stored_artifact = artifact(case, owner)
        other_artifact = artifact(other_case, owner)
        session.add_all([stored_artifact, other_artifact])
        await session.flush()
        protected = await persist_sensitive_value(
            session,
            case_id=case.id,
            evidence_id=stored_artifact.id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext="https://asgi-private.example/path",
            crypto=crypto_service,
        )
        other_value = await persist_sensitive_value(
            session,
            case_id=other_case.id,
            evidence_id=other_artifact.id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext="https://asgi-other-private.example/path",
            crypto=crypto_service,
        )
        await session.commit()
        case_id = case.id
        evidence_id = stored_artifact.id
        value_id = protected.id
        other_value_id = other_value.id

    app.state.sensitive_field_crypto = crypto_service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
            path = (
                f"/api/v1/cases/{case_id}/evidence/{evidence_id}/sensitive/"
                f"{value_id}/source_locator/reveal"
            )
            unauthenticated = await client.post(
                path,
                json={"reason": "Authentication failures must never be cacheable"},
            )
            assert unauthenticated.status_code == 401
            assert unauthenticated.headers["cache-control"] == "no-store"

            login = await client.post(
                "/api/v1/auth/login",
                headers={"Origin": "http://localhost:3000"},
                json={"username": "evidence-route-owner", "password": password},
            )
            assert login.status_code == 200
            csrf = client.cookies.get("darknetra_csrf")
            assert csrf
            missing_csrf = await client.post(
                path,
                json={"reason": "Missing CSRF must fail safely"},
            )
            assert missing_csrf.status_code == 403
            assert missing_csrf.headers["cache-control"] == "no-store"

            for alias_name in ("SOURCE_LOCATOR", "Source_Locator", "%20source_locator%20"):
                alias = await client.post(
                    path.replace("source_locator", alias_name),
                    headers={"X-CSRF-Token": csrf},
                    json={"reason": "Aliases must fail before cryptography"},
                )
                assert alias.status_code == 422
                assert alias.headers["cache-control"] == "no-store"

            revealed = await client.post(
                path,
                headers={"X-CSRF-Token": csrf},
                json={"reason": "Authorized provenance verification"},
            )
            assert revealed.status_code == 200
            assert revealed.headers["cache-control"] == "no-store"
            assert revealed.json() == {"value": "https://asgi-private.example/path"}

            async def failing_commit_session():
                async with async_session_factory() as failing_session:
                    async def fail_commit() -> None:
                        raise RuntimeError("synthetic reveal audit commit failure")

                    failing_session.commit = fail_commit  # type: ignore[method-assign]
                    yield failing_session

            app.dependency_overrides[get_db_session] = failing_commit_session
            failed_audit = await client.post(
                path,
                headers={"X-CSRF-Token": csrf},
                json={"reason": "Audit durability is mandatory"},
            )
            assert failed_audit.status_code == 500
            assert failed_audit.headers["cache-control"] == "no-store"
            assert "asgi-private" not in failed_audit.text
            assert "synthetic reveal audit commit failure" not in failed_audit.text
            app.dependency_overrides.pop(get_db_session, None)

            missing = await client.post(
                path.replace(str(value_id), str(uuid4())),
                headers={"X-CSRF-Token": csrf},
                json={"reason": "Unknown value should be hidden"},
            )
            assert missing.status_code == 404
            assert missing.headers["cache-control"] == "no-store"
            assert "asgi-private" not in missing.text

            cross_case = await client.post(
                path.replace(str(value_id), str(other_value_id)),
                headers={"X-CSRF-Token": csrf},
                json={"reason": "Cross-case protected values must remain hidden"},
            )
            assert cross_case.status_code == 404
            assert cross_case.headers["cache-control"] == "no-store"
            assert cross_case.json() == missing.json()
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        del app.state.sensitive_field_crypto


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unrelated_unexpected_failure_uses_fastapi_default_response() -> None:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as client:
        response = await client.get("/api/v1/test-only-unrelated-failure")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "Internal Server Error"
    assert "cache-control" not in response.headers


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
        retry_child = artifact(cases[0], owner)
        session.add_all([*artifacts, child, retry_child])
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

        lineage = build_evidence_derivation(
            case_id=cases[0].id,
            parent_evidence_id=artifacts[0].id,
            child_evidence_id=child.id,
            transformation="extract",
            transformer_version="1",
            parameters={"member": "safe.txt"},
        )
        session.add(lineage)
        await session.commit()

        duplicate_work = build_evidence_derivation(
            case_id=cases[0].id,
            parent_evidence_id=artifacts[0].id,
            child_evidence_id=retry_child.id,
            transformation="extract",
            transformer_version="1",
            parameters={"member": "safe.txt"},
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(duplicate_work)
                await session.flush()

        different_parameters = build_evidence_derivation(
            case_id=cases[0].id,
            parent_evidence_id=artifacts[0].id,
            child_evidence_id=child.id,
            transformation="extract",
            transformer_version="1",
            parameters={"member": "different.txt"},
        )
        session.add(different_parameters)
        await session.commit()

        cross_case_lineage = build_evidence_derivation(
            case_id=cases[0].id,
            parent_evidence_id=artifacts[0].id,
            child_evidence_id=artifacts[1].id,
            transformation="invalid-cross-case",
            transformer_version="1",
            parameters={},
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(cross_case_lineage)
                await session.flush()

        custody_note = build_sensitive_value(
            case_id=cases[0].id,
            evidence_id=artifacts[0].id,
            kind=EvidenceSensitiveValueKind.CUSTODY_NOTE,
            plaintext="valid custody note",
            crypto=crypto(),
        )
        wrong_note = build_sensitive_value(
            case_id=cases[0].id,
            evidence_id=artifacts[0].id,
            kind=EvidenceSensitiveValueKind.CONTACT,
            plaintext="not-a-custody-note@example.test",
            crypto=crypto(),
        )
        session.add_all([custody_note, wrong_note])
        await session.commit()

        invalid_custody = CustodyEvent(
            case_id=cases[0].id,
            evidence_id=artifacts[0].id,
            actor_user_id=owner.id,
            action="INVALID_NOTE_KIND",
            request_id="custody-wrong-kind",
            sensitive_note_id=wrong_note.id,
            sensitive_note_kind=EvidenceSensitiveValueKind.CUSTODY_NOTE,
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(invalid_custody)
                await session.flush()

        custody = CustodyEvent(
            case_id=cases[0].id,
            evidence_id=artifacts[0].id,
            actor_user_id=owner.id,
            action="PRESERVED",
            request_id="custody-append-only",
            integrity_sha256="a" * 64,
            sensitive_note_id=custody_note.id,
            sensitive_note_kind=EvidenceSensitiveValueKind.CUSTODY_NOTE,
            metadata_json={"location": "vault"},
        )
        session.add(custody)
        await session.commit()
        custody.action = "MUTATED"
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_blocks_bulk_manifest_and_custody_mutation() -> None:
    async with async_session_factory() as session:
        owner = user("database-invariant-owner", GlobalRole.CASE_OWNER)
        session.add(owner)
        await session.flush()
        case = Case(
            case_code="EVIDENCE-DB-INVARIANTS",
            title="Database invariants",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.flush()
        staging = EvidenceArtifact(
            case_id=case.id,
            source_class=EvidenceSourceClass.SYNTHETIC,
            source_type="provisional",
            acquisition_method="fixture",
            collector_user_id=owner.id,
            captured_at=datetime.now(UTC),
            state=EvidenceState.STAGING,
            size_bytes=1,
            sha256="1" * 64,
        )
        session.add(staging)
        await session.commit()
        staging_id = staging.id
        case_id = case.id
        owner_id = owner.id

        await session.execute(
            sa.update(EvidenceArtifact)
            .where(EvidenceArtifact.id == staging.id)
            .values(size_bytes=2, sha256="2" * 64)
        )
        await session.commit()

        preserved_without_sha512 = EvidenceArtifact(
            case_id=case.id,
            source_class=EvidenceSourceClass.SYNTHETIC,
            source_type="sha256-only",
            acquisition_method="fixture",
            collector_user_id=owner.id,
            captured_at=datetime.now(UTC),
            state=EvidenceState.STAGING,
        )
        session.add(preserved_without_sha512)
        await session.flush()
        preserve_evidence_manifest(
            preserved_without_sha512,
            media_type="application/octet-stream",
            size_bytes=0,
            sha256="6" * 64,
            object_key="sha256/66/" + "6" * 64,
        )
        await session.commit()
        assert preserved_without_sha512.sha512 is None
        await session.execute(
            sa.update(EvidenceArtifact)
            .where(EvidenceArtifact.id == staging.id)
            .values(
                state=EvidenceState.PRESERVED,
                size_bytes=3,
                sha256="3" * 64,
                sha512="4" * 128,
                object_key="sha256/33/" + "3" * 64,
            )
        )
        await session.commit()

        for statement in (
            sa.update(EvidenceArtifact)
            .where(EvidenceArtifact.id == staging.id)
            .values(sha256="5" * 64),
            sa.text("UPDATE evidence_artifacts SET object_key = 'changed' WHERE id = :id").bindparams(
                id=staging.id
            ),
        ):
            with pytest.raises(DBAPIError, match="preserved evidence manifest"):
                async with session.begin_nested():
                    await session.execute(statement)

        for rollback_statement in (
            sa.update(EvidenceArtifact)
            .where(EvidenceArtifact.id == staging.id)
            .values(state=EvidenceState.STAGING),
            sa.text("UPDATE evidence_artifacts SET state = 'STAGING' WHERE id = :id").bindparams(
                id=staging.id
            ),
        ):
            with pytest.raises(DBAPIError, match="cannot return to staging"):
                async with session.begin_nested():
                    await session.execute(rollback_statement)
            current_state = await session.scalar(
                select(EvidenceArtifact.state).where(EvidenceArtifact.id == staging.id)
            )
            assert current_state is EvidenceState.PRESERVED

        await session.refresh(staging)
        staging.state = EvidenceState.STAGING
        with pytest.raises(Exception, match="cannot return to staging"):
            await session.flush()
        await session.rollback()
        staging = await session.get(EvidenceArtifact, staging_id)
        assert staging is not None
        with pytest.raises(Exception, match="cannot return to staging"):
            update_artifact_metadata(staging, state=EvidenceState.STAGING)

        incomplete = EvidenceArtifact(
            case_id=case_id,
            source_class=EvidenceSourceClass.SYNTHETIC,
            source_type="invalid-incomplete",
            acquisition_method="fixture",
            collector_user_id=owner_id,
            captured_at=datetime.now(UTC),
            state=EvidenceState.PRESERVED,
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(incomplete)
                await session.flush()

        for invalid_object_key in ("\t", "\n", "\u00a0", "sha256/path with-space"):
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    await session.execute(
                        sa.insert(EvidenceArtifact).values(
                            id=uuid4(),
                            case_id=case_id,
                            source_class=EvidenceSourceClass.SYNTHETIC,
                            source_type="invalid-object-key",
                            acquisition_method="fixture",
                            collector_user_id=owner_id,
                            captured_at=datetime.now(UTC),
                            state=EvidenceState.PRESERVED,
                            size_bytes=1,
                            sha256="7" * 64,
                            object_key=invalid_object_key,
                        )
                    )

        custody = CustodyEvent(
            case_id=case_id,
            evidence_id=staging_id,
            actor_user_id=owner_id,
            action="PRESERVED",
            request_id="database-custody-invariant",
            integrity_sha256="3" * 64,
            metadata_json={},
        )
        session.add(custody)
        await session.commit()
        custody_id = custody.id
        runtime_statements = (
            sa.update(CustodyEvent)
            .where(CustodyEvent.id == custody_id)
            .values(action="MUTATED"),
            sa.delete(CustodyEvent).where(CustodyEvent.id == custody_id),
            sa.text("UPDATE custody_events SET action = 'DIRECT' WHERE id = :id").bindparams(
                id=custody_id
            ),
            sa.text("DELETE FROM custody_events WHERE id = :id").bindparams(id=custody_id),
        )
        for statement in runtime_statements:
            with pytest.raises(DBAPIError):
                async with session.begin_nested():
                    await session.execute(statement)

    settings = get_settings()
    owner_engine = create_async_engine(settings.database_owner_url or settings.database_url)
    owner_sessions = async_sessionmaker(owner_engine, expire_on_commit=False)
    async with owner_sessions() as owner_session:
        owner_statements = (
            sa.text("UPDATE custody_events SET action = 'OWNER' WHERE id = :id").bindparams(
                id=custody_id
            ),
            sa.text("DELETE FROM custody_events WHERE id = :id").bindparams(id=custody_id),
        )
        for statement in owner_statements:
            with pytest.raises(DBAPIError, match="append-only"):
                async with owner_session.begin_nested():
                    await owner_session.execute(statement)
    await owner_engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runtime_role_cannot_mutate_or_truncate_custody() -> None:
    settings = get_settings()
    if not settings.database_owner_url or settings.database_owner_url == settings.database_url:
        pytest.skip("distinct owner/runtime database URLs are required")

    async with async_session_factory() as session:
        current_user = await session.scalar(sa.text("SELECT current_user"))
        table_owner = await session.scalar(
            sa.text(
                "SELECT tableowner FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename = 'custody_events'"
            )
        )
        privileges = await session.execute(
            sa.text(
                "SELECT has_table_privilege(current_user, 'custody_events', 'SELECT'), "
                "has_table_privilege(current_user, 'custody_events', 'INSERT'), "
                "has_table_privilege(current_user, 'custody_events', 'UPDATE'), "
                "has_table_privilege(current_user, 'custody_events', 'DELETE'), "
                "has_table_privilege(current_user, 'custody_events', 'TRUNCATE'), "
                "has_schema_privilege(current_user, 'public', 'CREATE')"
            )
        )
        assert current_user != table_owner
        assert privileges.one() == (True, True, False, False, False, False)
        with pytest.raises(DBAPIError):
            await session.execute(sa.text("TRUNCATE custody_events"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_derives_canonical_parameters_digest_and_rejects_mismatch() -> None:
    samples = [
        {"z": [1, True, None], "a": {"é": "東京"}},
        {
            "positive_exponent": 1e20,
            "larger_positive_exponent": 1e23,
            "negative_exponent": -1e23,
            "integral_float": 1.0,
            "negative_zero": -0.0,
            "large_integer": 123456789012345678901234567890,
            "nested": [1e30, {"value": -3.0}],
        },
    ]
    async with async_session_factory() as session:
        for parameters in samples:
            database_digest = await session.scalar(
                sa.text("SELECT darknetra_derivation_parameters_digest(CAST(:value AS jsonb))").bindparams(
                    value=json.dumps(parameters, ensure_ascii=False)
                )
            )
            assert database_digest == derivation_parameters_digest(parameters)

        for unsupported in (1e-7, 1.5):
            with pytest.raises(DBAPIError, match="integer-valued"):
                async with session.begin_nested():
                    await session.scalar(
                        sa.text(
                            "SELECT darknetra_derivation_parameters_digest(CAST(:value AS jsonb))"
                        ).bindparams(value=json.dumps({"unsupported": unsupported}))
                    )

        owner = user("digest-authority-owner", GlobalRole.CASE_OWNER)
        session.add(owner)
        await session.flush()
        case = Case(
            case_code="EVIDENCE-DIGEST-AUTHORITY",
            title="Digest authority",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.flush()
        parent = artifact(case, owner)
        child = artifact(case, owner)
        session.add_all([parent, child])
        await session.flush()
        values = {
            "id": uuid4(),
            "case_id": case.id,
            "parent_evidence_id": parent.id,
            "child_evidence_id": child.id,
            "transformation": "extract",
            "transformer_version": "1",
            "parameters_json": {"member": "safe.txt"},
            "parameters_digest": "0" * 64,
        }
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(sa.insert(EvidenceDerivation).values(**values))

        valid = build_evidence_derivation(
            case_id=case.id,
            parent_evidence_id=parent.id,
            child_evidence_id=child.id,
            transformation="extract",
            transformer_version="1",
            parameters=samples[1],
        )
        session.add(valid)
        await session.commit()
        valid_id = valid.id
        session.expunge_all()
        loaded = await session.get(EvidenceDerivation, valid_id)
        assert loaded is not None
        assert loaded.parameters_json["positive_exponent"] == 100000000000000000000
        assert loaded.parameters_json["larger_positive_exponent"] == (
            100000000000000000000000
        )
        assert loaded.parameters_json["negative_exponent"] == (
            -100000000000000000000000
        )
        assert loaded.parameters_json["nested"][0] == (
            1000000000000000000000000000000
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    sa.update(EvidenceDerivation)
                    .where(EvidenceDerivation.id == valid.id)
                    .values(parameters_json={"member": "changed.txt"})
                )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_rejects_noncanonical_base64_padding_bits() -> None:
    crypto_service = crypto()
    async with async_session_factory() as session:
        owner = user("base64-canonical-owner", GlobalRole.CASE_OWNER)
        session.add(owner)
        await session.flush()
        case = Case(
            case_code="EVIDENCE-BASE64-CANONICAL",
            title="Base64 canonicality",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.flush()
        stored_artifact = artifact(case, owner)
        session.add(stored_artifact)
        await session.flush()
        value = build_sensitive_value(
            case_id=case.id,
            evidence_id=stored_artifact.id,
            kind=EvidenceSensitiveValueKind.CONTACT,
            plaintext="canonical-padding@example.test",
            crypto=crypto_service,
        )
        value.ciphertext_b64 = "AAAAAAAAAAAAAAAAAAAAAB=="
        with pytest.raises((ValueError, IntegrityError, DBAPIError)):
            async with session.begin_nested():
                await session.execute(
                    sa.insert(EvidenceSensitiveValue).values(
                        id=value.id,
                        case_id=value.case_id,
                        evidence_id=value.evidence_id,
                        kind=value.kind,
                        key_version=value.key_version,
                        nonce_b64=value.nonce_b64,
                        ciphertext_b64=value.ciphertext_b64,
                        blind_index=None,
                        policy_sensitive=True,
                    )
                )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_enforces_envelopes_blind_policy_and_locator_exact_dedup() -> None:
    crypto_service = crypto()
    async with async_session_factory() as session:
        owner = user("envelope-invariant-owner", GlobalRole.CASE_OWNER)
        session.add(owner)
        await session.flush()
        case = Case(
            case_code="EVIDENCE-ENVELOPE-INVARIANTS",
            title="Envelope invariants",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic authorized fixture",
        )
        session.add(case)
        await session.flush()
        artifacts = [artifact(case, owner) for _ in range(4)]
        session.add_all(artifacts)
        await session.flush()
        first = build_sensitive_value(
            case_id=case.id,
            evidence_id=artifacts[0].id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext="  HTTPS://Example.test/Path  ",
            crypto=crypto_service,
        )
        session.add(first)
        await session.commit()

        same_trimmed = build_sensitive_value(
            case_id=case.id,
            evidence_id=artifacts[1].id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext="HTTPS://Example.test/Path",
            crypto=crypto_service,
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(same_trimmed)
                await session.flush()

        case_distinct = build_sensitive_value(
            case_id=case.id,
            evidence_id=artifacts[2].id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext="https://example.test/Path",
            crypto=crypto_service,
        )
        path_distinct = build_sensitive_value(
            case_id=case.id,
            evidence_id=artifacts[3].id,
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            plaintext="https://example.test/path",
            crypto=crypto_service,
        )
        session.add_all([case_distinct, path_distinct])
        await session.commit()

        malformed = build_sensitive_value(
            case_id=case.id,
            evidence_id=artifacts[0].id,
            kind=EvidenceSensitiveValueKind.CONTACT,
            plaintext="contact@example.test",
            crypto=crypto_service,
        )
        malformed.nonce_b64 = "AAAA"
        with pytest.raises(ValueError, match="invalid encrypted field envelope"):
            async with session.begin_nested():
                session.add(malformed)
                await session.flush()

        valid_contact = build_sensitive_value(
            case_id=case.id,
            evidence_id=artifacts[0].id,
            kind=EvidenceSensitiveValueKind.CONTACT,
            plaintext="second-contact@example.test",
            crypto=crypto_service,
        )
        invalid_values = {
            "id": uuid4(),
            "case_id": case.id,
            "evidence_id": artifacts[0].id,
            "kind": EvidenceSensitiveValueKind.CONTACT,
            "key_version": valid_contact.key_version,
            "nonce_b64": "AAAA",
            "ciphertext_b64": valid_contact.ciphertext_b64,
            "blind_index": None,
            "policy_sensitive": True,
        }
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(sa.insert(EvidenceSensitiveValue).values(**invalid_values))

        invalid_locator = dict(invalid_values)
        invalid_locator.update(
            id=uuid4(),
            kind=EvidenceSensitiveValueKind.SOURCE_LOCATOR,
            nonce_b64=first.nonce_b64,
            ciphertext_b64=first.ciphertext_b64,
            blind_index=None,
        )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(sa.insert(EvidenceSensitiveValue).values(**invalid_locator))
