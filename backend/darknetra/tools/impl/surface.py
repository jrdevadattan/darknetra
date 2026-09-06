"""Read-only public-source adapters. All returned content passes the capture gate."""

from typing import Literal, cast
from urllib.parse import quote, urlencode

from pydantic import BaseModel, Field

from darknetra.capture.fetcher import SafeHttp
from darknetra.capture.gate import capture
from darknetra.tools.contracts import ToolContext, ToolError
from darknetra.tools.impl.evidence import Input


class QueryInput(Input):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(5, ge=1, le=10)


class UrlInput(Input):
    url: str = Field(min_length=1, max_length=4096)


class KeyInput(Input):
    fingerprint: str = Field(pattern=r"^[A-Fa-f0-9]{40}$")


class ChainInput(Input):
    address: str = Field(min_length=1, max_length=150)
    chain: Literal["BTC", "ETH", "TRON", "XMR"] = "BTC"


async def captured(ctx: ToolContext, tool: str, url: str) -> BaseModel:
    from darknetra.tools.registry import REGISTRY

    return await capture(ctx, spec=REGISTRY[tool], locator=url, fetch=lambda: SafeHttp().fetch(url))


async def fetch_page(ctx: ToolContext, args: BaseModel) -> BaseModel:
    return await captured(ctx, "fetch_page", cast(UrlInput, args).url)


async def web_search(ctx: ToolContext, args: BaseModel) -> BaseModel:
    return await captured(
        ctx,
        "web_search",
        "https://html.duckduckgo.com/html/?" + urlencode({"q": cast(QueryInput, args).query}),
    )


async def wayback_lookup(ctx: ToolContext, args: BaseModel) -> BaseModel:
    return await captured(
        ctx,
        "wayback_lookup",
        "https://archive.org/wayback/available?" + urlencode({"url": cast(UrlInput, args).url}),
    )


async def keyserver_lookup(ctx: ToolContext, args: BaseModel) -> BaseModel:
    return await captured(
        ctx,
        "keyserver_lookup",
        "https://keys.openpgp.org/vks/v1/by-fingerprint/"
        + cast(KeyInput, args).fingerprint.upper(),
    )


async def chain_lookup(ctx: ToolContext, args: BaseModel) -> BaseModel:
    args = cast(ChainInput, args)
    if args.chain != "BTC":
        raise ToolError("UNAVAILABLE", f"{args.chain} chain adapter is unavailable")
    return await captured(
        ctx, "chain_lookup", "https://mempool.space/api/address/" + quote(args.address, safe="")
    )


async def onion_search(ctx: ToolContext, args: BaseModel) -> BaseModel:
    return await captured(
        ctx,
        "onion_search",
        "https://ahmia.fi/search/?" + urlencode({"q": cast(QueryInput, args).query}),
    )


async def unavailable(ctx: ToolContext, args: BaseModel) -> BaseModel:
    raise ToolError(
        "UNAVAILABLE", "Optional source adapter is not available; no lookup was performed"
    )
