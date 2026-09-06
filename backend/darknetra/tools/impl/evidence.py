"""Evidence tools return bounded case-scoped derivatives, never original bytes."""

from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from darknetra.api.v1.schemas.search import SearchQuery
from darknetra.tools.contracts import ToolContext, ToolError


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadInput(Input):
    evidence_code: str = Field(pattern=r"^E-\d+$")
    kind: Literal["TEXT", "MESSAGES", "ROWS", "OCR"] = "TEXT"
    start_line: int = Field(1, ge=1)
    end_line: int | None = Field(None, ge=1)
    max_chars: int = Field(6000, ge=1, le=12000)


class ReadOutput(BaseModel):
    evidence_code: str
    evidence_id: UUID
    kind: str
    text: str
    start_line: int
    end_line: int
    truncated: bool


class EntityInput(Input):
    type: str | None = None
    q: str | None = Field(None, max_length=500)
    min_confidence: float = Field(0, ge=0, le=1)
    limit: int = Field(50, ge=1, le=200)


class EntitiesOutput(BaseModel):
    entities: list[dict[str, Any]]


class ExtractInput(Input):
    evidence_code: str = "all"


class ExtractOutput(BaseModel):
    run_ids: list[UUID]
    counts_by_type: dict[str, int]


class ImageInput(Input):
    evidence_code: str
    language_hint: str | None = None


class ImageOutput(BaseModel):
    blocks: list[dict[str, Any]]
    derivative_id: UUID


async def search_evidence(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.rag.search import search

    query = cast(SearchQuery, args).model_copy(deep=True)
    query.filters.include_quarantined = False
    async with ctx.session_factory() as session:
        return await search(session, ctx.case_id, query, actor=ctx.actor, settings=ctx.settings)


async def read_evidence(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.evidence.service import get_evidence, get_text

    args = cast(ReadInput, args)
    if args.kind != "TEXT":
        raise ToolError("UNAVAILABLE", "This reader exposes the canonical TEXT derivative only")
    async with ctx.session_factory() as session:
        evidence = await get_evidence(session, ctx.case_id, args.evidence_code)
        if evidence.status in {"QUARANTINED", "EXPIRED", "FAILED"}:
            raise ToolError("POLICY_DENIED", "Evidence is not available to models")
        text, _ = await get_text(session, ctx.case_id, evidence.id, ctx.settings)
        # Canonical derivative offsets and citation line numbers count LF only;
        # splitlines() also splits PDF form-feeds and shifts subsequent citations.
        lines = text.split("\n")
        end = min(args.end_line or len(lines), len(lines))
        selected = "\n".join(lines[args.start_line - 1 : end])
        bounded = selected[: args.max_chars]
        return ReadOutput(
            evidence_code=evidence.code,
            evidence_id=evidence.id,
            kind="TEXT",
            text=bounded,
            start_line=args.start_line,
            end_line=args.start_line + bounded.count("\n"),
            truncated=len(selected) > len(bounded) or end < len(lines),
        )


async def list_entities(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.evidence.models import Evidence
    from darknetra.extract.models import CanonicalEntity, Observation
    from darknetra.extract.visibility import current_observations

    args = cast(EntityInput, args)
    async with ctx.session_factory() as session:
        available = (
            current_observations(ctx.case_id)
            .with_only_columns(Observation.canonical_entity_id)
            .where(Observation.confidence >= args.min_confidence)
        )
        query = select(CanonicalEntity).where(
            CanonicalEntity.case_id == ctx.case_id, CanonicalEntity.id.in_(available)
        )
        if args.type:
            query = query.where(CanonicalEntity.type == args.type)
        if args.q:
            query = query.where(
                CanonicalEntity.display.ilike("%" + args.q.replace("%", "").replace("_", "") + "%")
            )
        rows = list(
            (
                await session.scalars(
                    query.order_by(CanonicalEntity.type, CanonicalEntity.id).limit(args.limit)
                )
            ).all()
        )
        output = []
        for entity in rows:
            observations = (
                await session.execute(
                    current_observations(ctx.case_id)
                    .add_columns(Evidence)
                    .where(
                        Observation.case_id == ctx.case_id,
                        Observation.canonical_entity_id == entity.id,
                        Observation.confidence >= args.min_confidence,
                    )
                    .limit(10)
                )
            ).all()
            if not observations:
                continue
            output.append(
                {
                    "id": str(entity.id),
                    "type": entity.type,
                    "display": "[masked]" if entity.type in {"PHONE", "EMAIL"} else entity.display,
                    "evidence_codes": sorted({e.code for _, e in observations}),
                    "evidence_spans": [
                        {
                            "evidence": {"id": str(e.id), "code": e.code},
                            "span": {"start": o.span_start, "end": o.span_end, "line": o.line_no},
                        }
                        for o, e in observations[:3]
                    ],
                }
            )
        return EntitiesOutput(entities=output)


async def extract_indicators(ctx: ToolContext, args: BaseModel) -> BaseModel:
    from darknetra.evidence.models import Derivative, Evidence
    from darknetra.extract.pipeline import run_evidence

    args = cast(ExtractInput, args)
    async with ctx.session_factory() as session:
        query = select(Evidence.id).where(
            Evidence.case_id == ctx.case_id,
            Evidence.status.in_(["READY", "PARTIAL"]),
            select(Derivative.id)
            .where(
                Derivative.case_id == ctx.case_id,
                Derivative.evidence_id == Evidence.id,
                Derivative.kind == "TEXT",
                Derivative.status == "READY",
            )
            .exists(),
        )
        if args.evidence_code != "all":
            query = query.where(Evidence.code == args.evidence_code)
        ids = list((await session.scalars(query.limit(200))).all())
        if not ids and args.evidence_code != "all":
            raise ToolError(
                "UNAVAILABLE", "No accessible text derivative is available for that evidence"
            )
        runs = []
        counts: dict[str, int] = {}
        for identifier in ids:
            run = await run_evidence(session, ctx.case_id, identifier, ctx.settings)
            runs.append(run.id)
            for kind, count in run.stats.get("counts", {}).items():
                counts[kind] = counts.get(kind, 0) + int(count)
        await session.commit()
        return ExtractOutput(run_ids=runs, counts_by_type=counts)


async def transcribe_image(ctx: ToolContext, args: BaseModel) -> BaseModel:
    raise ToolError("UNAVAILABLE", "Image transcription provider is not configured")
