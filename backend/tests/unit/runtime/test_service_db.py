"""Scenario 18/19/22/23/42: persisted runtime with synthetic actors and fake harness."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

import darknetra.models  # noqa: F401
from darknetra.agent.events import stream
from darknetra.agent.models import Message, Run, RunEvent
from darknetra.agent.service import create_thread, execute_run, post_message
from darknetra.api.v1.schemas.cases import SourcePolicy
from darknetra.api.v1.schemas.threads import MessageCreate, ThreadCreate
from darknetra.auth.actor import Actor
from darknetra.auth.models import User
from darknetra.cases.models import Case, CaseMembership
from darknetra.db import build_engine, build_session_factory
from darknetra.errors import BudgetExceeded, Conflict


@pytest.fixture
async def runtime(test_settings):
    engine = build_engine(test_settings)
    factory = build_session_factory(engine)
    async with factory() as db:
        user = User(
            id=uuid4(),
            username="synthetic-runtime-" + uuid4().hex,
            display_name="SYNTHETIC",
            password_hash="not-a-login-hash",
            global_role="INVESTIGATOR",
        )
        db.add(user)
        await db.flush()
        case = Case(
            id=uuid4(),
            code="SYN-RUN-" + uuid4().hex[:12],
            title="SYNTHETIC runtime",
            created_by=user.id,
            source_policy=SourcePolicy().model_dump(),
        )
        db.add(case)
        await db.flush()
        db.add(CaseMembership(case_id=case.id, user_id=user.id, role="OWNER", added_by=user.id))
        await db.commit()
        actor = Actor("USER", user.id, global_role="INVESTIGATOR", user_id=user.id)
    app = SimpleNamespace(state=SimpleNamespace(session_factory=factory, settings=test_settings))
    try:
        yield app, case, actor
    finally:
        await engine.dispose()


async def queued(runtime, *, budget=2):
    app, case, actor = runtime
    async with app.state.session_factory() as db:
        thread = await create_thread(
            db, case, actor, ThreadCreate(title="SYNTHETIC", budget_usd=budget), app.state.settings
        )
        await db.commit()
        run = await post_message(
            db,
            case.id,
            actor,
            thread.id,
            MessageCreate(content="SYNTHETIC question"),
            app.state.settings,
        )
    return thread, run


@pytest.mark.integration
async def test_fake_invalid_claim_persisted_and_revised_once(runtime):
    app, case, actor = runtime
    calls = []

    class FakeHarness:
        async def run(self, ctx, prompt, **kwargs):
            calls.append(prompt)
            yield {"type": "assistant", "text": "SYNTHETIC claim [E-9999]"}
            yield {"type": "usage", "cost_usd": "0.1"}

    app.state.harness_factory = lambda mode: FakeHarness()
    thread, run = await queued(runtime)
    await execute_run(app, case.id, thread.id, run.id, actor, "SYNTHETIC question")
    async with app.state.session_factory() as db:
        persisted = await db.scalar(select(Run).where(Run.case_id == case.id, Run.id == run.id))
        messages = list(
            (
                await db.scalars(
                    select(Message).where(
                        Message.case_id == case.id,
                        Message.run_id == run.id,
                        Message.role == "ASSISTANT",
                    )
                )
            ).all()
        )
        assert persisted.status == "DONE"
        assert str(persisted.cost_usd) == "0.2000"
        assert len(calls) == 2
        assert len(messages) == 2 and all(not m.verification["ok"] for m in messages)
    events = [event async for event in stream(app.state.session_factory, case.id, run.id)]
    sequences = [int(event["id"]) for event in events]
    assert sequences == list(range(1, len(events) + 1))
    replay = [
        event async for event in stream(app.state.session_factory, case.id, run.id, sequences[-2])
    ]
    assert len(replay) == 1 and replay[0]["event"] == "run.finished"


@pytest.mark.integration
async def test_concurrent_thread_and_budget_guard(runtime):
    app, case, actor = runtime
    thread, run = await queued(runtime)
    async with app.state.session_factory() as db:
        with pytest.raises(Conflict):
            await post_message(
                db,
                case.id,
                actor,
                thread.id,
                MessageCreate(content="SYNTHETIC second"),
                app.state.settings,
            )
    with pytest.raises(BudgetExceeded):
        await queued(runtime, budget=0.2)


@pytest.mark.integration
async def test_cancel_preserves_partial_and_verifies(runtime):
    app, case, actor = runtime
    ready = asyncio.Event()

    class FakeHarness:
        async def run(self, ctx, prompt, **kwargs):
            yield {"type": "message.delta", "data": {"text": "SYNTHETIC partial [E-9999]"}}
            ready.set()
            await asyncio.Event().wait()

    app.state.harness_factory = lambda mode: FakeHarness()
    thread, run = await queued(runtime)
    task = asyncio.create_task(execute_run(app, case.id, thread.id, run.id, actor, "SYNTHETIC"))
    await asyncio.wait_for(ready.wait(), timeout=10)
    task.cancel()
    await task
    async with app.state.session_factory() as db:
        persisted = await db.scalar(select(Run).where(Run.case_id == case.id, Run.id == run.id))
        partial = await db.scalar(
            select(Message).where(
                Message.case_id == case.id, Message.run_id == run.id, Message.role == "ASSISTANT"
            )
        )
        assert persisted.status == "CANCELLED"
        assert partial.text == "SYNTHETIC partial [E-9999]"
        assert partial.verification["ok"] is False
        terminal = await db.scalar(
            select(RunEvent).where(
                RunEvent.case_id == case.id,
                RunEvent.run_id == run.id,
                RunEvent.type == "run.cancelled",
            )
        )
        assert terminal is not None


@pytest.mark.integration
async def test_startup_recovery_closes_interrupted_run_and_unblocks_thread(runtime):
    from darknetra.agent.service import recover_interrupted_runs

    app, case, actor = runtime
    thread, run = await queued(runtime)
    recovered = await recover_interrupted_runs(app)
    assert recovered >= 1
    async with app.state.session_factory() as db:
        persisted = await db.scalar(select(Run).where(Run.case_id == case.id, Run.id == run.id))
        assert persisted.status == "ERROR" and persisted.error["code"] == "UNAVAILABLE"
        assert not list(
            await db.scalars(
                select(Message).where(
                    Message.case_id == case.id,
                    Message.run_id == run.id,
                    Message.role == "ASSISTANT",
                )
            )
        )
        next_run = await post_message(
            db,
            case.id,
            actor,
            thread.id,
            MessageCreate(content="SYNTHETIC resumed"),
            app.state.settings,
        )
        assert next_run.status == "QUEUED"
    events = [event async for event in stream(app.state.session_factory, case.id, run.id)]
    assert [event["event"] for event in events][-2:] == ["run.error", "run.finished"]
