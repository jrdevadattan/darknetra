"""Bounded public search/feed adapters; parse only after immutable capture succeeds."""

import io
import json
from importlib.metadata import version
from typing import Any, Literal, cast
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from uuid import UUID

import feedparser
from pydantic import BaseModel, Field
from selectolax.parser import HTMLParser

from darknetra.capture.fetcher import Fetched, SafeHttp, validate_url
from darknetra.capture.gate import CaptureResult, capture
from darknetra.integrations.public_text import extract_public_text
from darknetra.tools.contracts import ToolContext, ToolError
from darknetra.tools.impl.evidence import Input
from darknetra.tools.presentation import emit_parsing

MAX_PARSE_BYTES = 2 * 1024 * 1024


class SurfaceSearchInput(Input):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(5, ge=1, le=10)
    provider: Literal["duckduckgo", "searxng"] = "duckduckgo"


class RssReadInput(Input):
    url: str = Field(min_length=1, max_length=4096)
    limit: int = Field(5, ge=1, le=10)


class PublicPageInput(Input):
    url: str = Field(min_length=1, max_length=4096)


class PublicPageOutput(BaseModel):
    capture: CaptureResult
    text: str = Field(default="", max_length=12000)
    extraction_method: str | None = None
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False


class SourceEntry(BaseModel):
    title: str
    url: str
    excerpt: str
    evidence_code: str
    evidence_id: UUID


class SurfaceSearchOutput(BaseModel):
    capture: CaptureResult
    provider: str
    hits: list[SourceEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False


class RssReadOutput(BaseModel):
    capture: CaptureResult
    title: str = ""
    entries: list[SourceEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False


def plain_text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    tree = HTMLParser(value[:20000])
    for node in tree.css("script,style"):
        node.decompose()
    return " ".join(tree.text(separator=" ").split())[:limit]


def safe_result_url(value: Any, base: str) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or any(ord(c) < 33 for c in value)
    ):
        return None
    try:
        url = urljoin(base, value)
        validate_url(url)
    except (ToolError, ValueError):
        return None
    return url


async def captured_bytes(ctx: ToolContext, tool: str, url: str) -> tuple[CaptureResult, Fetched]:
    from darknetra.tools.registry import REGISTRY

    fetched: Fetched | None = None

    async def fetch() -> Fetched:
        nonlocal fetched
        fetched = await SafeHttp().fetch(url)
        if len(fetched.data) > MAX_PARSE_BYTES:
            raise ToolError("VALIDATION", "Research response exceeds 2 MiB parsing limit")
        return fetched

    result = await capture(ctx, spec=REGISTRY[tool], locator=url, fetch=fetch)
    if fetched is None:
        raise ToolError("UNAVAILABLE", "Capture did not provide source bytes")
    return result, fetched


def entries_from_rows(
    rows: list[dict[str, Any]], capture_result: CaptureResult, base: str, limit: int
) -> tuple[list[SourceEntry], list[str], bool]:
    entries: list[SourceEntry] = []
    seen: set[str] = set()
    warnings: list[str] = []
    truncated = len(rows) > 100
    for row in rows[:100]:
        url = safe_result_url(row.get("url"), base)
        if url is None:
            if "Unsafe or onion links omitted; onion access requires the dark lane" not in warnings:
                warnings.append(
                    "Unsafe or onion links omitted; onion access requires the dark lane"
                )
            continue
        if url in seen:
            continue
        seen.add(url)
        if len(entries) == limit:
            truncated = True
            continue
        entries.append(
            SourceEntry(
                title=plain_text(row.get("title"), 300),
                url=url,
                excerpt=plain_text(row.get("content"), 1200),
                evidence_code=capture_result.evidence_code,
                evidence_id=capture_result.evidence_id,
            )
        )
    return entries, warnings, truncated


def parse_search(
    data: bytes, provider: str, capture_result: CaptureResult, base: str, limit: int
) -> SurfaceSearchOutput:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    if provider == "searxng":
        try:
            payload = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            raise ToolError("UNAVAILABLE", "Search provider returned invalid JSON") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ToolError("UNAVAILABLE", "Search provider returned an invalid result schema")
        rows = [row for row in payload["results"] if isinstance(row, dict)]
        if payload.get("unresponsive_engines"):
            warnings.append("One or more search engines were unavailable")
            if not rows:
                raise ToolError("UNAVAILABLE", "Search engines failed without returning results")
    else:
        tree = HTMLParser(data)
        for result in tree.css(".result"):
            anchor = result.css_first(".result__a")
            if anchor is None:
                continue
            target = anchor.attributes.get("href", "")
            try:
                parsed = urlsplit(urljoin(base, target))
                if parsed.hostname in {
                    "duckduckgo.com",
                    "html.duckduckgo.com",
                } and parsed.path.startswith("/l/"):
                    target = parse_qs(parsed.query).get("uddg", [target])[0]
            except ValueError:
                target = ""
            snippet = result.css_first(".result__snippet")
            rows.append(
                {
                    "title": anchor.text(),
                    "url": target,
                    "content": snippet.text() if snippet else "",
                }
            )
        if not rows and tree.css_first(".no-results") is None:
            raise ToolError("UNAVAILABLE", "Search page contains no recognizable results")
    hits, excluded, truncated = entries_from_rows(rows, capture_result, base, limit)
    return SurfaceSearchOutput(
        capture=capture_result,
        provider=provider,
        hits=hits,
        warnings=warnings + excluded,
        truncated=truncated,
    )


async def surface_search(ctx: ToolContext, args: BaseModel) -> BaseModel:
    inputs = cast(SurfaceSearchInput, args)
    if inputs.provider == "searxng":
        # SearXNG splits directives on whitespace before choosing engines.
        # Engine/category bangs and language directives must not override the
        # operator-reviewed upstream selection (including external !! bangs).
        if any(part.startswith(("!", ":")) for part in inputs.query.split()):
            raise ToolError("VALIDATION", "SearXNG query directives are not allowed")
        endpoint = getattr(ctx.settings, "surface_search_searxng_url", None)
        if not endpoint:
            raise ToolError("UNAVAILABLE", "SearXNG endpoint is not configured")
        validate_url(endpoint)
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or parsed.query or parsed.fragment:
            raise ToolError(
                "POLICY_DENIED", "SearXNG requires public HTTPS without query or fragment"
            )
        url = (
            endpoint
            + "?"
            + urlencode({"q": inputs.query, "format": "json", "engines": "bing,brave"})
        )
    else:
        url = "https://html.duckduckgo.com/html/?" + urlencode({"q": inputs.query})
    result, fetched = await captured_bytes(ctx, "surface_search", url)
    if result.quarantined:
        return SurfaceSearchOutput(
            capture=result, provider=inputs.provider, warnings=["Captured source is quarantined"]
        )
    await emit_parsing(ctx, "surface_search", result)
    return parse_search(fetched.data, inputs.provider, result, fetched.url, inputs.limit)


def parse_feed(data: bytes, result: CaptureResult, base: str, limit: int) -> RssReadOutput:
    # A bytes argument also permits feedparser's filename fallback. A stream
    # guarantees that this parser sees only the bytes persisted by capture.
    feed = feedparser.parse(io.BytesIO(data))
    if not feed.get("version"):
        raise ToolError("UNAVAILABLE", "Source is not a recognized RSS, Atom or JSON feed")
    rows = [
        {
            "title": entry.get("title", ""),
            "url": entry.get("link"),
            "content": entry.get("summary", ""),
        }
        for entry in feed.entries
    ]
    entries, warnings, truncated = entries_from_rows(rows, result, base, limit)
    if feed.get("bozo"):
        warnings.append("Feed contains parsing errors; entries may be incomplete")
    return RssReadOutput(
        capture=result,
        title=plain_text(feed.feed.get("title"), 300),
        entries=entries,
        warnings=warnings,
        truncated=truncated,
    )


async def rss_read(ctx: ToolContext, args: BaseModel) -> BaseModel:
    inputs = cast(RssReadInput, args)
    result, fetched = await captured_bytes(ctx, "rss_read", inputs.url)
    if result.quarantined:
        return RssReadOutput(capture=result, warnings=["Captured source is quarantined"])
    await emit_parsing(ctx, "rss_read", result)
    return parse_feed(fetched.data, result, fetched.url, inputs.limit)


async def public_page_read(ctx: ToolContext, args: BaseModel) -> BaseModel:
    inputs = cast(PublicPageInput, args)
    result, fetched = await captured_bytes(ctx, "public_page_read", inputs.url)
    if result.quarantined:
        return PublicPageOutput(capture=result, warnings=["Captured source is quarantined"])
    if fetched.mime not in {"text/html", "application/xhtml+xml"}:
        raise ToolError("UNAVAILABLE", "Article extraction requires an HTML response")
    await emit_parsing(ctx, "public_page_read", result)
    text = extract_public_text(fetched.data) or ""
    return PublicPageOutput(
        capture=result,
        text=text,
        extraction_method="trafilatura/" + version("trafilatura"),
        warnings=[] if text else ["No main article text could be extracted"],
        truncated=len(text) == 12000,
    )
