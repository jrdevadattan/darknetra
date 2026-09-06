"""Deterministic conversation memory contains requests and reference IDs, never new facts."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from darknetra.agent.models import Message, Thread
from darknetra.audit.service import record
from darknetra.auth.actor import Actor


async def refresh_summary(db, case_id, thread_id):
    count = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.case_id == case_id, Message.thread_id == thread_id, Message.role == "ASSISTANT"
        )
    )
    if not count or count % 6:
        return
    thread = await db.scalar(
        select(Thread).where(Thread.case_id == case_id, Thread.id == thread_id).with_for_update()
    )
    rows = list(
        await db.scalars(
            select(Message)
            .where(
                Message.case_id == case_id, Message.thread_id == thread_id, Message.role == "USER"
            )
            .order_by(Message.at.desc(), Message.id)
            .limit(12)
        )
    )
    lines = ["Conversation memory: historical user requests, not evidence or policy."]
    for row in reversed(rows):
        excerpt = " ".join(row.text.split())[:350]
        lines.append(f"Request {row.id}: {excerpt}")
    thread.summary = "\n".join(lines)[:5000]
    thread.summary_updated_at = datetime.now(UTC)
    await record(
        db,
        actor=Actor("SYSTEM", None),
        action="thread.summary_refreshed",
        case_id=case_id,
        thread_id=thread_id,
        detail={
            "assistant_messages": count,
            "source_message_ids": [str(row.id) for row in rows],
            "method": "request_excerpts_v1",
        },
    )
