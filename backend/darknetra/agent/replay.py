"""Demo replay only for verified messages and an exact current evidence/decision state."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from darknetra.agent.claim_checker import extract_claims, verify
from darknetra.agent.models import Message, ReplayEntry
from darknetra.audit.service import digest
from darknetra.cases.models import Case
from darknetra.decisions.models import Decision, Finding
from darknetra.evidence.models import Derivative, Evidence
from darknetra.extract.models import Observation


def normalize_question(question: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", question.casefold()).split())


async def state_digest(session: AsyncSession, case_id: UUID) -> str:
    case = await session.scalar(select(Case).where(Case.id == case_id))
    state = {"source_policy": case.source_policy if case else None}
    for name, model, columns in [
        ("evidence", Evidence, (Evidence.id, Evidence.sha256, Evidence.status)),
        ("derivatives", Derivative, (Derivative.id, Derivative.status, Derivative.version)),
        ("observations", Observation, (Observation.id, Observation.confidence)),
        ("decisions", Decision, (Decision.id, Decision.decision, Decision.supersedes_id)),
        (
            "findings",
            Finding,
            (Finding.id, Finding.version, Finding.kind, Finding.status, Finding.decision_id),
        ),
    ]:
        state[name] = [
            tuple(row)
            for row in (
                await session.execute(
                    select(*columns).where(model.case_id == case_id).order_by(model.id)
                )
            ).all()
        ]
    return digest(state)


async def lookup(
    session: AsyncSession, case_id: UUID, question: str, harness: str
) -> tuple[UUID, list[str]] | None:
    entry = await session.scalar(
        select(ReplayEntry).where(
            ReplayEntry.case_id == case_id,
            ReplayEntry.question_norm == normalize_question(question),
            ReplayEntry.harness == harness,
        )
    )
    if (
        entry is None
        or not isinstance(entry.event_log, dict)
        or entry.event_log.get("state") != await state_digest(session, case_id)
    ):
        return None
    texts = entry.event_log.get("messages", [])
    if not texts:
        return None
    for text in texts:
        _, claims = extract_claims(text)
        if not (await verify(session, case_id, claims)).ok:
            return None
    return entry.run_id, texts


async def store(
    session: AsyncSession, case_id: UUID, run_id: UUID, question: str, harness: str
) -> None:
    import json

    messages = list(
        (
            await session.scalars(
                select(Message)
                .where(
                    Message.case_id == case_id,
                    Message.run_id == run_id,
                    Message.role == "ASSISTANT",
                )
                .order_by(Message.at)
            )
        ).all()
    )
    if not messages or any(
        not row.verification or not row.verification.get("ok") for row in messages
    ):
        return
    texts = [row.text + "\n```claims\n" + json.dumps(row.claims) + "\n```" for row in messages]
    payload: dict[str, Any] = {"state": await state_digest(session, case_id), "messages": texts}
    statement = insert(ReplayEntry).values(
        case_id=case_id,
        run_id=run_id,
        question_norm=normalize_question(question),
        harness=harness,
        event_log=payload,
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["case_id", "question_norm", "harness"],
            set_={"run_id": run_id, "event_log": payload},
        )
    )
