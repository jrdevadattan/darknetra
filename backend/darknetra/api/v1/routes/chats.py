import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from darknetra.api.v1.schemas import chats as dto
from darknetra.api.v1.schemas.common import Page
from darknetra.auth.actor import Actor
from darknetra.authz.deps import current_actor
from darknetra.chats import service
from darknetra.chats.models import PrivateMessage, PrivateThread
from darknetra.db import get_session
from darknetra.errors import Conflict, Forbidden, NotFound, Validation

router = APIRouter(tags=["private chats"])


async def owner_actor(actor: Actor = Depends(current_actor)):
    if actor.kind != "USER" or actor.user_id is None:
        raise Forbidden("Private chats require an interactive human session")
    return actor


@router.post("/chats", response_model=dto.Chat, status_code=201)
async def create_chat(
    data: dto.ChatCreate,
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    chat = PrivateThread(owner_user_id=actor.user_id, **data.model_dump())
    db.add(chat)
    await db.flush()
    await service.audit(db, actor.user_id, "private.chat.created", chat.id, "PRIVATE_CHAT")
    return chat


@router.get("/chats", response_model=Page[dto.Chat])
async def list_chats(
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    query = select(PrivateThread).where(PrivateThread.owner_user_id == actor.user_id)
    if cursor:
        previous = await service.get_chat(db, actor.user_id, cursor)
        query = query.where(
            tuple_(PrivateThread.created_at, PrivateThread.id) < (previous.created_at, previous.id)
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(PrivateThread.created_at.desc(), PrivateThread.id.desc()).limit(
                    limit + 1
                )
            )
        ).all()
    )
    return Page(
        items=[dto.Chat.model_validate(r) for r in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.get("/chats/{chat_id}", response_model=dto.Chat)
async def get_chat(
    chat_id: UUID,
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await service.get_chat(db, actor.user_id, chat_id)


@router.patch("/chats/{chat_id}", response_model=dto.Chat)
async def patch_chat(
    chat_id: UUID,
    data: dto.ChatPatch,
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    chat = await service.get_chat(db, actor.user_id, chat_id, lock=True)
    from darknetra.chats.models import PrivateRun

    active = await db.scalar(
        select(PrivateRun.id).where(
            PrivateRun.owner_user_id == actor.user_id,
            PrivateRun.thread_id == chat_id,
            PrivateRun.status.in_(["QUEUED", "RUNNING"]),
        )
    )
    if active:
        raise Conflict("Wait for or cancel the active run before editing the chat")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            raise Validation("Chat fields cannot be null")
        if key == "budget_usd" and value < chat.spent_usd:
            raise Validation("Budget cannot be below reported spend")
        setattr(chat, key, value)
    await service.audit(db, actor.user_id, "private.chat.updated", chat_id, "PRIVATE_CHAT")
    await db.flush()
    await db.refresh(chat)
    return chat


@router.get("/chats/{chat_id}/messages", response_model=Page[dto.Message])
async def messages(
    chat_id: UUID,
    cursor: UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    await service.get_chat(db, actor.user_id, chat_id)
    query = select(PrivateMessage).where(
        PrivateMessage.owner_user_id == actor.user_id, PrivateMessage.thread_id == chat_id
    )
    if cursor:
        previous = await db.scalar(query.where(PrivateMessage.id == cursor))
        if previous is None:
            raise NotFound("Resource not found")
        query = query.where(
            tuple_(PrivateMessage.at, PrivateMessage.id) > (previous.at, previous.id)
        )
    rows = list(
        (
            await db.scalars(query.order_by(PrivateMessage.at, PrivateMessage.id).limit(limit + 1))
        ).all()
    )
    return Page(
        items=[dto.Message.model_validate(r) for r in rows[:limit]],
        next_cursor=str(rows[limit - 1].id) if len(rows) > limit else None,
    )


@router.post("/chats/{chat_id}/messages", response_model=dto.RunRef, status_code=202)
async def post_message(
    chat_id: UUID,
    data: dto.MessageCreate,
    request: Request,
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    run = await service.post_message(db, actor.user_id, chat_id, data.content)
    if not hasattr(request.app.state, "private_runtime_jobs"):
        request.app.state.private_runtime_jobs = {}
    try:
        job = await request.app.state.jobs.submit(
            "private.run",
            lambda: service.execute_run(request.app, actor.user_id, chat_id, run.id),
            key=f"private-run:{run.id}",
        )
        request.app.state.private_runtime_jobs[run.id] = job
    except Exception:
        await service.terminalize(
            request.app.state.session_factory,
            actor.user_id,
            chat_id,
            run.id,
            "ERROR",
            {"code": "UNAVAILABLE", "message": "Job runner unavailable"},
        )
        return dto.RunRef(run_id=run.id, chat_id=chat_id, status="ERROR")
    return dto.RunRef(run_id=run.id, chat_id=chat_id, status="QUEUED")


@router.get("/chats/{chat_id}/runs/{run_id}", response_model=dto.Run)
async def get_run(
    chat_id: UUID,
    run_id: UUID,
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    return await service.get_run(db, actor.user_id, chat_id, run_id)


@router.get(
    "/chats/{chat_id}/runs/{run_id}/events",
    response_class=Response,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def events(
    chat_id: UUID,
    run_id: UUID,
    request: Request,
    last_event_id: str | None = Header(None),
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    await service.get_run(db, actor.user_id, chat_id, run_id)
    try:
        after = int(last_event_id or "0")
        if after < 0:
            raise ValueError
    except ValueError:
        raise Validation("Last-Event-ID must be a nonnegative sequence") from None
    return EventSourceResponse(
        service.stream(request.app.state.session_factory, actor.user_id, chat_id, run_id, after),
        ping=15,
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/chats/{chat_id}/runs/{run_id}/cancel", status_code=202)
async def cancel(
    chat_id: UUID,
    run_id: UUID,
    request: Request,
    actor: Actor = Depends(owner_actor),
    db: AsyncSession = Depends(get_session, scope="function"),
):
    run = await service.get_run(db, actor.user_id, chat_id, run_id, lock=True)
    if run.status not in service.TERMINAL:
        run.cancel_requested = True
        await service.audit(db, actor.user_id, "private.run.cancel_requested", run_id)
        await service.finish(db, run, "CANCELLED")
        await db.commit()
        job = getattr(request.app.state, "private_runtime_jobs", {}).get(run_id)
        if job:
            # asyncio.wait does not wait indefinitely for cancellation suppression.
            task = asyncio.create_task(request.app.state.jobs.cancel(job))
            if not hasattr(request.app.state, "private_cancellation_tasks"):
                request.app.state.private_cancellation_tasks = set()
            tasks = request.app.state.private_cancellation_tasks
            tasks.add(task)

            def completed(done):
                tasks.discard(done)
                if not done.cancelled():
                    done.exception()

            task.add_done_callback(completed)
            await asyncio.wait({task}, timeout=2)
    return Response(status_code=202)
