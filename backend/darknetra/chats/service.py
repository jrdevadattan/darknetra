"""Transactional owner boundary and public lifecycle for private conversations."""

import asyncio
import json
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import func, select

from darknetra.audit.service import record
from darknetra.auth.actor import Actor
from darknetra.auth.models import User
from darknetra.chats import providers
from darknetra.chats.models import PrivateMessage, PrivateRun, PrivateRunEvent, PrivateThread
from darknetra.errors import AppError, BudgetExceeded, Conflict, Forbidden, NotFound, RateLimited

TERMINAL = {"DONE", "ERROR", "CANCELLED", "BUDGET"}


async def require_active_owner(db, owner):
    user = await db.scalar(select(User).where(User.id == owner))
    if user is None or not user.is_active or user.must_change_password:
        raise Forbidden("Private chat owner is no longer authorized")


async def get_chat(db, owner, chat_id, lock=False):
    query = select(PrivateThread).where(
        PrivateThread.owner_user_id == owner, PrivateThread.id == chat_id
    )
    row = await db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise NotFound("Resource not found")
    return row


async def get_run(db, owner, chat_id, run_id, lock=False):
    query = select(PrivateRun).where(
        PrivateRun.owner_user_id == owner, PrivateRun.thread_id == chat_id, PrivateRun.id == run_id
    )
    row = await db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise NotFound("Resource not found")
    return row


async def audit(db, owner, action, target, kind="PRIVATE_RUN"):
    await record(
        db,
        actor=Actor("USER", owner, user_id=owner),
        action=action,
        target_type=kind,
        target_id=target,
    )


async def append(db, run, event, data):
    seq = await db.scalar(
        select(func.coalesce(func.max(PrivateRunEvent.seq), 0)).where(
            PrivateRunEvent.owner_user_id == run.owner_user_id, PrivateRunEvent.run_id == run.id
        )
    )
    db.add(
        PrivateRunEvent(
            owner_user_id=run.owner_user_id, run_id=run.id, seq=seq + 1, type=event, data=data
        )
    )
    await db.flush()


async def post_message(db, owner, chat_id, content):
    # Serialize owner-wide admission before the thread lock.
    await db.scalar(select(User).where(User.id == owner).with_for_update())
    chat = await get_chat(db, owner, chat_id, lock=True)
    if chat.status != "OPEN":
        raise Conflict("Chat is closed")
    active = list(
        (
            await db.scalars(
                select(PrivateRun).where(
                    PrivateRun.owner_user_id == owner, PrivateRun.status.in_(["QUEUED", "RUNNING"])
                )
            )
        ).all()
    )
    if any(r.thread_id == chat_id for r in active):
        raise Conflict("Chat already has an active run")
    if len(active) >= 3:
        raise RateLimited("Private chat concurrency limit reached")
    if chat.budget_usd - chat.spent_usd < Decimal("0.0001"):
        raise BudgetExceeded("Chat budget exhausted")
    run = PrivateRun(owner_user_id=owner, thread_id=chat_id, provider=chat.provider)
    db.add(run)
    await db.flush()
    db.add(
        PrivateMessage(
            owner_user_id=owner,
            thread_id=chat_id,
            run_id=run.id,
            role="USER",
            text=content,
            blocks=[],
        )
    )
    chat.last_message_at = datetime.now(UTC)
    await audit(db, owner, "private.message.created", chat_id, "PRIVATE_CHAT")
    await audit(db, owner, "private.run.queued", run.id)
    await db.commit()
    return run


async def finish(db, run, status, error=None):
    if run.status in TERMINAL:
        return
    run.status, run.finished_at, run.error = status, datetime.now(UTC), error
    if error:
        await append(db, run, "run.error", error)
    if status == "CANCELLED":
        await append(db, run, "run.cancelled", {})
    await append(
        db,
        run,
        "run.finished",
        {
            "status": status,
            "cost_usd": str(run.cost_usd),
            "cost_complete": run.cost_complete,
            "tokens_in": run.tokens_in,
            "tokens_out": run.tokens_out,
        },
    )
    await audit(db, run.owner_user_id, "private.run." + status.lower(), run.id)


async def terminalize(factory, owner, chat_id, run_id, status, error=None):
    async with factory() as db:
        run = await get_run(db, owner, chat_id, run_id, lock=True)
        await finish(db, run, status, error)
        await db.commit()


async def execute_run(app, owner, chat_id, run_id):
    factory = app.state.session_factory
    try:
        async with factory() as db:
            run = await get_run(db, owner, chat_id, run_id, lock=True)
            if run.status in TERMINAL:
                return
            chat = await get_chat(db, owner, chat_id)
            run.status, run.started_at = "RUNNING", datetime.now(UTC)
            await append(db, run, "run.started", {"status": "RUNNING"})
            await audit(db, owner, "private.run.started", run.id)
            await db.commit()
            await require_active_owner(db, owner)
            provider = await providers.select_provider(run.provider, app.state.settings)
            run.provider = provider
            budget = chat.budget_usd - chat.spent_usd
            rows = list(
                (
                    await db.scalars(
                        select(PrivateMessage)
                        .where(
                            PrivateMessage.owner_user_id == owner,
                            PrivateMessage.thread_id == chat_id,
                        )
                        .order_by(PrivateMessage.at.desc(), PrivateMessage.id.desc())
                        .limit(20)
                    )
                ).all()
            )
            history = [
                {"role": m.role.lower(), "content": m.text[:8000]}
                for m in reversed(rows)
                if m.role in {"USER", "ASSISTANT"}
            ]
            await db.commit()
        async with factory() as db:
            await require_active_owner(db, owner)
        async with asyncio.timeout(app.state.settings.nim_timeout_seconds):
            async for event in providers.generate(provider, app.state.settings, history, budget):
                async with factory() as db:
                    run = await get_run(db, owner, chat_id, run_id, lock=True)
                    if run.status in TERMINAL:
                        return
                    await require_active_owner(db, owner)
                    if run.cancel_requested:
                        await finish(db, run, "CANCELLED")
                        await db.commit()
                        return
                    if event["type"] == "assistant":
                        content = event["text"][:65536]
                        chat = await get_chat(db, owner, chat_id, lock=True)
                        chat.last_message_at = datetime.now(UTC)
                        message = PrivateMessage(
                            owner_user_id=owner,
                            thread_id=chat_id,
                            run_id=run_id,
                            role="ASSISTANT",
                            text=content,
                            blocks=[],
                            provider=provider,
                        )
                        db.add(message)
                        await db.flush()
                        await append(
                            db,
                            run,
                            "message.completed",
                            {
                                "message_id": str(message.id),
                                "text": content,
                                "verification": {
                                    "mode": "NOT_APPLICABLE",
                                    "reason": "private_chat_has_no_case_evidence",
                                },
                            },
                        )
                        await audit(db, owner, "private.message.created", chat_id, "PRIVATE_CHAT")
                    elif event["type"] == "usage":
                        chat = await get_chat(db, owner, chat_id, lock=True)
                        # Four-decimal storage conservatively over-reserves less than
                        # USD 0.0001 per reported charge; positive costs never round away.
                        cost = event["cost_usd"].quantize(Decimal("0.0001"), rounding=ROUND_CEILING)
                        run.cost_usd += cost
                        chat.spent_usd += cost
                        run.tokens_in += event["tokens_in"]
                        run.tokens_out += event["tokens_out"]
                        run.cost_complete = event["cost_complete"]
                        if chat.spent_usd >= chat.budget_usd:
                            await finish(
                                db,
                                run,
                                "BUDGET",
                                {"code": "BUDGET_EXCEEDED", "message": "Chat budget exhausted"},
                            )
                    await db.commit()
        await terminalize(factory, owner, chat_id, run_id, "DONE")
    except asyncio.CancelledError:
        await terminalize(factory, owner, chat_id, run_id, "CANCELLED")
        raise
    except Exception as exc:
        error = {
            "code": exc.code if isinstance(exc, AppError) else "UNAVAILABLE",
            "message": exc.message
            if isinstance(exc, AppError)
            else "Private chat provider could not complete this run",
        }
        await terminalize(
            factory,
            owner,
            chat_id,
            run_id,
            "BUDGET" if error["code"] == "BUDGET_EXCEEDED" else "ERROR",
            error,
        )
    finally:
        getattr(app.state, "private_runtime_jobs", {}).pop(run_id, None)


async def recover_interrupted(factory):
    async with factory() as db:
        # Startup administrative inventory only; every mutation below is owner-scoped.
        abandoned = list(
            (
                await db.execute(
                    select(PrivateRun.owner_user_id, PrivateRun.thread_id, PrivateRun.id).where(
                        PrivateRun.status.in_(["QUEUED", "RUNNING"])
                    )
                )
            ).all()
        )
    for owner, chat_id, run_id in abandoned:
        await terminalize(
            factory,
            owner,
            chat_id,
            run_id,
            "ERROR",
            {"code": "UNAVAILABLE", "message": "Private run interrupted by service restart"},
        )


async def stream(factory, owner, chat_id, run_id, after):
    while True:
        async with factory() as db:
            run = await get_run(db, owner, chat_id, run_id)
            rows = list(
                (
                    await db.scalars(
                        select(PrivateRunEvent)
                        .where(
                            PrivateRunEvent.owner_user_id == owner,
                            PrivateRunEvent.run_id == run_id,
                            PrivateRunEvent.seq > after,
                        )
                        .order_by(PrivateRunEvent.seq)
                        .limit(200)
                    )
                ).all()
            )
            done = run.status in TERMINAL
        for row in rows:
            yield {"id": str(row.seq), "event": row.type, "data": json.dumps(row.data)}
            after = row.seq
        if done and len(rows) < 200:
            return
        await asyncio.sleep(0.1)
