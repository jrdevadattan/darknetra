from __future__ import annotations

import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import CaseSensitivity
from darknetra_api.models.job import Job, JobState
from darknetra_api.models.user import User
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError


def _redis_url() -> str:
    value = os.getenv("DARKNETRA_REDIS_URL")
    if not value:
        pytest.skip("DARKNETRA_REDIS_URL is required for Redis durability integration tests")
    return value


async def _clean() -> None:
    async with async_session_factory() as session:
        await session.execute(sa.delete(Job))
        await session.execute(sa.delete(CaseMembershipRole))
        await session.execute(sa.delete(CaseMembership))
        await session.execute(sa.delete(AuditEvent))
        await session.execute(sa.delete(Case))
        await session.execute(sa.delete(AuthSession))
        await session.execute(sa.delete(User))
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_jobs() -> None:
    await _clean()
    yield
    await _clean()


async def _seed_case() -> Case:
    async with async_session_factory() as session:
        username = f"job-owner-{uuid4().hex[:8]}"
        owner = User(
            username=username,
            username_normalized=username.casefold(),
            display_name="Synthetic Job Owner",
            password_hash="unused",
            global_roles=[],
            is_active=True,
            must_change_password=False,
        )
        session.add(owner)
        await session.flush()
        case = Case(
            case_code=f"JOB-{uuid4().hex[:10].upper()}",
            title="Durable job boundary",
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Authorized synthetic test",
        )
        session.add(case)
        await session.commit()
        await session.refresh(case)
        return case


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_history_survives_redis_flush() -> None:
    case = await _seed_case()
    job_id = uuid4()
    idempotency_key = f"ingest:{job_id}:v1"

    async with async_session_factory() as session:
        session.add(
            Job(
                id=job_id,
                case_id=case.id,
                resource_type="evidence",
                resource_id=str(uuid4()),
                task_name="darknetra.ingestion.process_evidence",
                queue="ingest",
                idempotency_key=idempotency_key,
                state=JobState.PENDING,
            )
        )
        await session.commit()

    redis = Redis.from_url(_redis_url(), decode_responses=True)
    try:
        await redis.set("darknetra:test:delivery", "transient")
        await redis.flushdb()
        assert await redis.get("darknetra:test:delivery") is None
    finally:
        await redis.aclose()

    async with async_session_factory() as session:
        persisted = await session.get(Job, job_id)
        assert persisted is not None
        assert persisted.idempotency_key == idempotency_key
        assert persisted.state is JobState.PENDING
        assert persisted.attempt_count == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_idempotency_key_is_unique() -> None:
    case = await _seed_case()
    key = f"ingest:{uuid4()}:v1"
    async with async_session_factory() as session:
        session.add_all(
            [
                Job(
                    case_id=case.id,
                    resource_type="evidence",
                    resource_id=str(uuid4()),
                    task_name="darknetra.ingestion.process_evidence",
                    queue="ingest",
                    idempotency_key=key,
                ),
                Job(
                    case_id=case.id,
                    resource_type="evidence",
                    resource_id=str(uuid4()),
                    task_name="darknetra.ingestion.process_evidence",
                    queue="ingest",
                    idempotency_key=key,
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()
