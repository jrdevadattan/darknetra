"""Robin-derived index parsing over one captured public Ahmia response."""

from typing import Literal, cast
from urllib.parse import urlencode
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from darknetra.api.v1.schemas.common import SourceClass
from darknetra.capture.fetcher import Fetched, SafeHttp
from darknetra.capture.gate import CaptureResult, capture
from darknetra.integrations.robin import UPSTREAM_COMMIT, IndexFormatError, parse_index
from darknetra.tools.contracts import ToolContext, ToolError
from darknetra.tools.impl.evidence import Input
from darknetra.tools.presentation import emit_parsing


class RobinSearchInput(Input):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Search query must contain text")
        return value


class RobinIndexHit(BaseModel):
    title: str = Field(max_length=300)
    url: str = Field(max_length=4096)
    excerpt: str = Field(max_length=300)
    evidence_code: str
    evidence_id: UUID
    observation_kind: Literal["INDEX_ENTRY"] = "INDEX_ENTRY"
    target_fetched: Literal[False] = False


class RobinSearchOutput(CaptureResult):
    source_class: SourceClass
    hits: list[RobinIndexHit] = Field(default_factory=list, max_length=10)
    upstream_commit: str = UPSTREAM_COMMIT
    scope: str = (
        "Observations from a captured public search index. Target pages were not fetched; "
        "entries do not establish service availability, ownership, or current content."
    )


async def robin_search(ctx: ToolContext, args: BaseModel) -> RobinSearchOutput:
    from darknetra.tools.registry import REGISTRY

    request = cast(RobinSearchInput, args)
    url = "https://ahmia.fi/search/?" + urlencode({"q": request.query})
    fetched: Fetched | None = None

    async def fetch() -> Fetched:
        nonlocal fetched
        fetched = await SafeHttp().fetch(url)
        return fetched

    # The holder is local to this invocation/case. No parsing occurs until the
    # gate has successfully persisted the exact response and returned evidence.
    result = await capture(ctx, spec=REGISTRY["robin_search"], locator=url, fetch=fetch)
    output = RobinSearchOutput.model_validate(result.model_dump())
    if result.quarantined:
        return output
    if fetched is None or fetched.mime not in {"text/html", "application/xhtml+xml"}:
        raise ToolError("UNAVAILABLE", "Captured index did not provide supported HTML")
    await emit_parsing(ctx, "robin_search", result)
    try:
        hits = parse_index(fetched.data, limit=request.limit)
    except IndexFormatError as exc:
        raise ToolError("UNAVAILABLE", str(exc)) from None
    except ValueError as exc:
        raise ToolError("VALIDATION", str(exc)) from None
    output.hits = [
        RobinIndexHit(
            title=hit.title,
            url=hit.url,
            excerpt=hit.title,
            evidence_code=result.evidence_code,
            evidence_id=result.evidence_id,
        )
        for hit in hits
    ]
    return output
