import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from darknetra_api.db.session import async_session_factory
from darknetra_api.models.audit import AuditEvent
from darknetra_api.models.auth_session import AuthSession
from darknetra_api.models.case import Case
from darknetra_api.models.case_membership import CaseMembership, CaseMembershipRole
from darknetra_api.models.enums import CaseSensitivity, JobStatus
from darknetra_api.models.job import AnalysisJob
from darknetra_api.models.user import User
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError


def redis_url() -> str:
    value = os.getenv("DARKNETRA_REDIS_URL")
    if not value:
        pytest.skip("DARKNETRA_REDIS_URL is required for job broker integration tests")
    return value


async def clear_database() -> None:
    async with async_session_factory() as session:
        for model in (
            AnalysisJob,
            CaseMembershipRole,
            CaseMembership,
            AuditEvent,
            Case,
            AuthSession,
            User,
        ):
            await session.execute(sa.delete(model))
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_database() -> None:
    await clear_database()
    yield
    await clear_database()


async def seed_case() -> Case:
    async with async_session_factory() as session:
        suffix = uuid4().hex[:12]
        owner = User(
            username=f"job-owner-{suffix}",
            username_normalized=f"job-owner-{suffix}",
            display_name="Job Owner",
            password_hash="not-used",
            global_roles=[],
            is_active=True,
            must_change_password=False,
        )
        session.add(owner)
        await session.flush()
        case = Case(
            case_code=f"JOB-{suffix.upper()}",
            title="Durable job case",
            sensitivity=CaseSensitivity.STANDARD,
            owner_user_id=owner.id,
            source_authority_summary="Synthetic integration fixture",
        )
        session.add(case)
        await session.commit()
        await session.refresh(case)
        return case


def make_job(case: Case, *, idempotency_key: str) -> AnalysisJob:
    return AnalysisJob(
        case_id=case.id,
        resource_type="evidence",
        resource_id=uuid4(),
        task_name="darknetra.ingestion.process_evidence",
        queue="ingest",
        idempotency_key=idempotency_key,
        status=JobStatus.PENDING,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pending_job_history_survives_redis_flush() -> None:
    case = await seed_case()
    job = make_job(case, idempotency_key=f"ingest:{uuid4()}")
    async with async_session_factory() as session:
        session.add(job)
        await session.commit()
        job_id = job.id
        idempotency_key = job.idempotency_key

    redis = Redis.from_url(redis_url(), decode_responses=True)
    try:
        await redis.set(f"transient-job:{job_id}", "queued")
        await redis.flushdb()
        assert await redis.get(f"transient-job:{job_id}") is None
    finally:
        await redis.aclose()

    async with async_session_factory() as session:
        persisted = await session.get(AnalysisJob, job_id)

    assert persisted is not None
    assert persisted.status is JobStatus.PENDING
    assert persisted.idempotency_key == idempotency_key
    assert persisted.attempt_count == 0
    assert persisted.created_at is not None
    assert persisted.started_at is None
    assert persisted.finished_at is None
    assert persisted.error_code is None
    assert persisted.error_message is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_idempotency_key_is_unique() -> None:
    case = await seed_case()
    key = f"ingest:{uuid4()}"
    async with async_session_factory() as session:
        session.add_all([make_job(case, idempotency_key=key), make_job(case, idempotency_key=key)])

        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_attempt_count_cannot_be_negative() -> None:
    case = await seed_case()
    job = make_job(case, idempotency_key=f"ingest:{uuid4()}")
    job.attempt_count = -1
    async with async_session_factory() as session:
        session.add(job)

        with pytest.raises(IntegrityError):
            await session.commit()
