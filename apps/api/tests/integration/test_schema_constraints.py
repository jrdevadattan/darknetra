from uuid import uuid4

import pytest
import sqlalchemy as sa
from darknetra_api.config import get_settings
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership
from darknetra_api.models.enums import CaseSensitivity, CaseStatus
from darknetra_api.models.user import User
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def _clear_schema() -> None:
    settings = get_settings()
    owner_engine = create_async_engine(settings.database_owner_url or settings.database_url)
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
async def clean_schema() -> None:
    await _clear_schema()
    yield
    await _clear_schema()


def make_user(username: str, *, is_active: bool = True) -> User:
    return User(
        username=username,
        username_normalized=username.casefold(),
        display_name=username,
        password_hash="schema-test-hash",
        global_roles=[],
        is_active=is_active,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_normalized_username_is_unique() -> None:
    async with async_session_factory() as session:
        session.add(make_user("AnalystOne"))
        await session.commit()
        session.add(make_user("ANALYSTONE"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_disabled_user_flag_is_persisted() -> None:
    async with async_session_factory() as session:
        user = make_user("disabled-user", is_active=False)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        assert user.is_active is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_case_code_is_unique() -> None:
    async with async_session_factory() as session:
        owner = make_user("case-owner")
        session.add(owner)
        await session.flush()
        case_one = Case(
            case_code="CHD-001",
            title="First case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Authorized training source",
        )
        case_two = Case(
            case_code="CHD-001",
            title="Second case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Authorized training source",
        )
        session.add_all([case_one, case_two])
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_case_membership_is_unique_per_user_and_case() -> None:
    async with async_session_factory() as session:
        owner = make_user("membership-owner")
        member = make_user("membership-user")
        session.add_all([owner, member])
        await session.flush()
        case = Case(
            case_code="CHD-002",
            title="Membership case",
            status=CaseStatus.OPEN,
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Authorized training source",
        )
        session.add(case)
        await session.flush()
        session.add_all(
            [
                CaseMembership(case_id=case.id, user_id=member.id),
                CaseMembership(case_id=case.id, user_id=member.id),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_events_are_append_only_at_orm_boundary() -> None:
    async with async_session_factory() as session:
        event = AuditEvent(
            actor_user_id=None,
            event_type="SCHEMA_TEST",
            resource_type="system",
            resource_id=str(uuid4()),
            case_id=None,
            request_id=str(uuid4()),
            metadata_json={"purpose": "append-only contract"},
        )
        session.add(event)
        await session.commit()
        event.event_type = "MUTATED"
        with pytest.raises(RuntimeError, match="append-only"):
            await session.commit()
