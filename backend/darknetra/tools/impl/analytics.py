"""Model tools call deterministic analytics; confirmation remains a human API action."""

from collections.abc import Awaitable, Callable
from typing import cast
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Select, or_

from darknetra.analytics.models import AnalyticRun, LinkCandidate, TrendBucket, WalletAssessment
from darknetra.api.v1.schemas import analytics as dto
from darknetra.api.v1.schemas.common import EvidenceRef
from darknetra.authz.permissions import Permission
from darknetra.tools.contracts import ToolContext
from darknetra.tools.impl.evidence import Input
from darknetra.tools.impl.shared import authorize, observation_sources


class CorrelationOutput(BaseModel):
    result: dto.CorrelateResult
    candidates: list[dto.LinkCandidate]
    truncated: bool


class GraphInput(Input):
    focus: UUID | None = None
    depth: int = Field(1, ge=0, le=2)
    include_pending: bool = True
    include_rejected: bool = False
    include_evidence: bool = True


class GraphOutput(BaseModel):
    graph: dto.GraphDTO
    evidence: list[EvidenceRef]


class WalletOutput(BaseModel):
    assessment: dto.WalletAssessment
    evidence: list[EvidenceRef]


class TrendInput(Input):
    window_days: int = Field(30, ge=1, le=366)
    term: str | None = Field(None, max_length=200)


class TrendOutput(BaseModel):
    trends: dto.Trends
    evidence: list[EvidenceRef]


async def correlate_entities(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.analytics.correlate import run_case
    from darknetra.analytics.graph import latest_links
    from darknetra.analytics.serialization import link_dto

    options = cast(dto.CorrelateRequest, args)
    run_service = cast(Callable[..., Awaitable[AnalyticRun]], run_case)
    serialize = cast(Callable[..., Awaitable[dto.LinkCandidate]], link_dto)
    select_current = cast(Callable[[UUID], Select[tuple[LinkCandidate]]], latest_links)
    async with ctx.session_factory() as session:
        await authorize(ctx, session, Permission.THREAD_RUN)
        run = await run_service(
            session, ctx.case_id, ctx.actor, ctx.settings, focus_entity_id=options.focus_entity_id
        )
        statement = select_current(ctx.case_id)
        if options.focus_entity_id:
            statement = statement.where(
                or_(
                    LinkCandidate.subject_a_id == options.focus_entity_id,
                    LinkCandidate.subject_b_id == options.focus_entity_id,
                )
            )
        rows = list(
            (
                await session.scalars(
                    statement.order_by(LinkCandidate.score.desc(), LinkCandidate.id).limit(21)
                )
            ).all()
        )
        result = CorrelationOutput(
            result=dto.CorrelateResult(
                run_id=run.id,
                candidates_created=run.stats.get("candidates_created", 0),
                candidates_rescored=run.stats.get("candidates_rescored", 0),
            ),
            candidates=[await serialize(session, row) for row in rows[:20]],
            truncated=len(rows) > 20,
        )
        await session.commit()
    await ctx.emit(
        {
            "type": "store.changed",
            "data": {"case_id": str(ctx.case_id), "tables": ["link_candidates", "graph_edges"]},
        }
    )
    return result


async def graph(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.analytics.graph import query

    service = cast(Callable[..., Awaitable[dto.GraphDTO]], query)
    async with ctx.session_factory() as session:
        await authorize(ctx, session, Permission.EVIDENCE_VIEW)
        result = await service(session, ctx.case_id, **cast(GraphInput, args).model_dump())
        refs = await observation_sources(
            session,
            ctx.case_id,
            entity_ids=[node.id for node in result.nodes if node.type != "EVIDENCE"],
        )
        return GraphOutput(graph=result, evidence=refs)


async def assess_wallet(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.analytics.serialization import wallet_dto
    from darknetra.analytics.wallets import assess_wallet as assess

    service = cast(Callable[..., Awaitable[WalletAssessment]], assess)
    serialize = cast(Callable[..., Awaitable[dto.WalletAssessment]], wallet_dto)
    async with ctx.session_factory() as session:
        case = await authorize(ctx, session, Permission.THREAD_RUN)
        row = await service(
            session, case, ctx.actor, cast(dto.WalletAssessRequest, args), ctx.settings
        )
        result = WalletOutput(
            assessment=await serialize(session, row),
            evidence=await observation_sources(session, ctx.case_id, address=row.address),
        )
        await session.commit()
        return result


async def detect_trends(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.analytics.trends import candidates, compute_buckets

    options = cast(TrendInput, args)
    compute = cast(Callable[..., Awaitable[list[TrendBucket]]], compute_buckets)
    describe = cast(Callable[..., Awaitable[dto.Trends]], candidates)
    async with ctx.session_factory() as session:
        await authorize(ctx, session, Permission.EVIDENCE_VIEW)
        buckets = await compute(
            session, ctx.case_id, window_days=options.window_days, persist=False
        )
        trends = await describe(
            session,
            ctx.case_id,
            window_days=options.window_days,
            term=options.term,
            buckets=buckets,
        )
        return TrendOutput(trends=trends, evidence=await observation_sources(session, ctx.case_id))
