"""Agent Reach's public web channel, with DARKNETRA transport and capture.

The pinned upstream WebChannel supplies URL checks and challenge detection. Its
direct urllib reader is intentionally replaced so persistence precedes exposure.
"""

from typing import Literal, cast

from agent_reach.channels.web import _is_antibot_page
from agent_reach.utils.url import normalize_public_http_url
from pydantic import BaseModel, Field

from darknetra.capture.fetcher import Fetched, SafeHttp, validate_url
from darknetra.capture.gate import CaptureResult, capture
from darknetra.tools.contracts import ToolContext, ToolError
from darknetra.tools.impl.evidence import Input


class ReaderInput(Input):
    url: str = Field(min_length=1, max_length=4096)


class ReaderOutput(BaseModel):
    capture: CaptureResult
    requested_url: str
    representation: Literal["JINA_READER"] = "JINA_READER"
    origin_verified: Literal[False] = False
    limitation: str = (
        "Captured Jina Reader representation, not an independently verified origin response. "
        "The requested public URL is disclosed to Jina Reader."
    )


async def agent_reach_read(ctx: ToolContext, args: BaseModel) -> ReaderOutput:
    from darknetra.tools.registry import REGISTRY

    request = cast(ReaderInput, args)
    try:
        target = str(normalize_public_http_url(request.url))
    except ValueError:
        raise ToolError("POLICY_DENIED", "Only public HTTP(S) targets are allowed") from None
    validate_url(target)
    url = "https://r.jina.ai/" + target
    fetched: Fetched | None = None

    async def fetch() -> Fetched:
        nonlocal fetched
        fetched = await SafeHttp().fetch(url)
        return fetched

    result = await capture(ctx, spec=REGISTRY["agent_reach_read"], locator=url, fetch=fetch)
    if not result.quarantined:
        if fetched is None or fetched.mime not in {"text/plain", "text/markdown"}:
            raise ToolError("UNAVAILABLE", "Captured reader response is not supported text")
        if len(fetched.data) > 5 * 1024 * 1024:
            raise ToolError("VALIDATION", "Captured reader response exceeds 5 MiB")
        if _is_antibot_page(fetched.data):
            raise ToolError("UNAVAILABLE", "Reader returned a verification challenge, not content")
    return ReaderOutput(capture=result, requested_url=target)
