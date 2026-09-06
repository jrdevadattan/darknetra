"""Synthetic provider responses verify immutable capture precedes bounded parsing."""

import importlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from darknetra.capture.fetcher import Fetched
from darknetra.capture.gate import CaptureResult
from darknetra.tools.contracts import ToolError


@pytest.fixture
def research(monkeypatch):
    module = importlib.import_module("darknetra.tools.impl.research")
    from darknetra.tools.registry import REGISTRY

    for name, source in [
        ("surface_search", "web_search"),
        ("rss_read", "fetch_page"),
        ("public_page_read", "fetch_page"),
    ]:
        if name not in REGISTRY:
            monkeypatch.setitem(REGISTRY, name, replace(REGISTRY[source], name=name))
    return module


@pytest.fixture
def captured_source(monkeypatch, research):
    """Replace only external HTTP and DB persistence; keep parsing and bounds real."""
    state = SimpleNamespace(body=b"", mime="application/json", committed=False, calls=[])
    record = CaptureResult(
        evidence_code="E-0042",
        evidence_id=uuid4(),
        duplicate=False,
        excerpt="SYNTHETIC captured source",
        source_class="OSINT_SURFACE",
        captured_at=datetime.now(UTC),
        quarantined=False,
    )

    async def fetch(self, url, method="GET"):
        state.calls.append((url, method))
        return Fetched(state.body, state.mime, url, 200, {}, datetime.now(UTC))

    async def capture(ctx, *, spec, locator, fetch):
        fetched = await fetch()
        assert fetched.data == state.body
        state.committed = True
        return record

    monkeypatch.setattr(research.SafeHttp, "fetch", fetch)
    monkeypatch.setattr(research, "capture", capture)
    state.record = record
    return state


def context(url=None):
    return SimpleNamespace(settings=SimpleNamespace(surface_search_searxng_url=url))


async def test_search_only_parses_after_capture_and_bounds_hits(
    research, captured_source, monkeypatch
):
    state = captured_source
    state.body = json.dumps(
        {
            "results": [
                {
                    "title": f"SYNTHETIC {i}",
                    "url": f"https://example.org/page/{i}",
                    "content": "x" * 3000,
                }
                for i in range(15)
            ]
        }
    ).encode()
    parse = research.parse_search

    def checked_parse(*args, **kwargs):
        assert state.committed, "Search content was parsed before evidence persistence"
        return parse(*args, **kwargs)

    monkeypatch.setattr(research, "parse_search", checked_parse)
    result = await research.surface_search(
        context("https://example.org/search"),
        research.SurfaceSearchInput(query="SYNTHETIC docs", provider="searxng", limit=2),
    )
    assert len(result.hits) == 2
    assert result.hits[0].title == "SYNTHETIC 0"
    assert len(result.hits[0].excerpt) <= 1200
    assert result.capture.evidence_code == "E-0042"
    assert result.hits[0].evidence_id == state.record.evidence_id
    assert result.truncated
    assert state.calls == [
        ("https://example.org/search?q=SYNTHETIC+docs&format=json&engines=bing%2Cbrave", "GET")
    ]


async def test_search_filters_private_and_credential_links(research, captured_source):
    captured_source.body = json.dumps(
        {
            "results": [
                {"title": "SYNTHETIC unsafe", "url": "http://127.0.0.1/admin"},
                {"title": "SYNTHETIC unsafe", "url": "https://user:secret@example.org"},
                {"title": "SYNTHETIC unsafe", "url": "javascript:alert(1)"},
                {"title": "SYNTHETIC valid", "url": "https://example.org/page"},
                {"title": "SYNTHETIC duplicate", "url": "https://example.org/page"},
            ]
        }
    ).encode()
    result = await research.surface_search(
        context("https://example.org/search"),
        research.SurfaceSearchInput(query="SYNTHETIC", provider="searxng"),
    )
    assert [hit.url for hit in result.hits] == ["https://example.org/page"]
    assert result.warnings


@pytest.mark.parametrize(
    "url",
    [
        None,
        "http://example.org/search",
        "https://127.0.0.1/search",
        "https://example.org/search?api_key=secret",
    ],
)
async def test_search_rejects_missing_or_unsafe_endpoint_before_fetch(
    research, captured_source, url
):
    with pytest.raises(ToolError):
        await research.surface_search(
            context(url), research.SurfaceSearchInput(query="SYNTHETIC", provider="searxng")
        )
    assert captured_source.calls == []


async def test_duckduckgo_unwraps_result_without_fetching_destination(research, captured_source):
    captured_source.mime = "text/html"
    captured_source.body = b'<html><div class="result"><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fdocs">SYNTHETIC docs</a><a class="result__snippet">SYNTHETIC excerpt</a></div></html>'
    result = await research.surface_search(
        context(), research.SurfaceSearchInput(query="SYNTHETIC")
    )
    assert [(hit.url, hit.excerpt) for hit in result.hits] == [
        ("https://example.org/docs", "SYNTHETIC excerpt")
    ]
    assert len(captured_source.calls) == 1


async def test_feed_parses_captured_bytes_and_filters_unsafe_links(
    research, captured_source, monkeypatch
):
    state = captured_source
    state.mime = "application/rss+xml"
    state.body = b"""<rss version="2.0"><channel><title>SYNTHETIC feed</title>
      <item><title>SYNTHETIC good</title><link>https://example.org/post</link><description>&lt;b&gt;SYNTHETIC summary&lt;/b&gt;</description></item>
      <item><title>SYNTHETIC unsafe</title><link>http://169.254.169.254/latest/</link></item>
      <item><title>SYNTHETIC good two</title><link>https://example.org/post2</link></item>
    </channel></rss>"""
    parse = research.parse_feed

    def checked_parse(*args, **kwargs):
        assert state.committed, "Feed parsed before evidence persistence"
        return parse(*args, **kwargs)

    monkeypatch.setattr(research, "parse_feed", checked_parse)
    result = await research.rss_read(
        context(), research.RssReadInput(url="https://example.org/feed.xml", limit=1)
    )
    assert result.title == "SYNTHETIC feed"
    assert [entry.url for entry in result.entries] == ["https://example.org/post"]
    assert result.entries[0].excerpt == "SYNTHETIC summary"
    assert result.entries[0].evidence_code == "E-0042"
    assert result.truncated
    assert len(state.calls) == 1


async def test_oversized_feed_fails_before_parser(research, captured_source, monkeypatch):
    captured_source.body = b"x" * (2 * 1024 * 1024 + 1)
    monkeypatch.setattr(research, "parse_feed", lambda *args: pytest.fail("Oversized feed parsed"))
    with pytest.raises(ToolError, match="exceeds"):
        await research.rss_read(context(), research.RssReadInput(url="https://example.org/feed"))


async def test_quarantined_response_is_not_parsed(research, captured_source, monkeypatch):
    captured_source.record.quarantined = True
    monkeypatch.setattr(
        research, "parse_feed", lambda *args: pytest.fail("Quarantined feed parsed")
    )
    result = await research.rss_read(
        context(), research.RssReadInput(url="https://example.org/feed")
    )
    assert result.entries == []
    assert result.capture.quarantined


async def test_persistence_failure_prevents_feed_parsing(research, monkeypatch):
    async def denied(*args, **kwargs):
        raise ToolError("POLICY_DENIED", "SYNTHETIC denial")

    monkeypatch.setattr(research, "capture", denied)
    monkeypatch.setattr(
        research, "parse_feed", lambda *args: pytest.fail("Uncaptured content parsed")
    )
    with pytest.raises(ToolError, match="SYNTHETIC denial"):
        await research.rss_read(context(), research.RssReadInput(url="https://example.org/feed"))


@pytest.mark.parametrize("url", ["http://[invalid", "", "\nhttps://example.org/page", "http://"])
def test_malformed_result_urls_are_omitted(research, url):
    assert research.safe_result_url(url, "https://example.org/feed") is None


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b'{"error":"SYNTHETIC unavailable"}',
        b'{"results":[],"unresponsive_engines":[["test","timeout"]]}',
    ],
)
async def test_invalid_search_provider_response_fails_after_capture(
    research, captured_source, payload
):
    captured_source.body = payload
    with pytest.raises(ToolError):
        await research.surface_search(
            context("https://example.org/search"),
            research.SurfaceSearchInput(query="SYNTHETIC", provider="searxng"),
        )
    assert captured_source.committed


async def test_non_feed_document_returns_explicit_error(research, captured_source):
    captured_source.body = b"<html><body>SYNTHETIC not a feed</body></html>"
    with pytest.raises(ToolError, match="recognized"):
        await research.rss_read(context(), research.RssReadInput(url="https://example.org/feed"))
    assert captured_source.committed


async def test_public_page_extracts_actual_article_after_capture(
    research, captured_source, monkeypatch
):
    state = captured_source
    state.mime = "text/html"
    paragraph = "SYNTHETIC documentation explains the public evidence archive and its provenance. "
    state.body = (
        "<html><body><nav>SYNTHETIC menu</nav><article><h1>SYNTHETIC article</h1><p>"
        + paragraph * 12
        + "</p></article></body></html>"
    ).encode()
    extract = research.extract_public_text

    def checked_extract(*args, **kwargs):
        assert state.committed, "Article extraction ran before persistence"
        return extract(*args, **kwargs)

    monkeypatch.setattr(research, "extract_public_text", checked_extract)
    result = await research.public_page_read(
        context(), research.PublicPageInput(url="https://example.org/article")
    )
    assert "SYNTHETIC documentation explains" in result.text
    assert "SYNTHETIC menu" not in result.text
    assert result.extraction_method.startswith("trafilatura")
    assert len(result.text) <= 12000
    assert result.capture.evidence_code == "E-0042"


async def test_public_page_does_not_extract_quarantined_source(
    research, captured_source, monkeypatch
):
    captured_source.record.quarantined = True
    monkeypatch.setattr(
        research, "extract_public_text", lambda *args: pytest.fail("Quarantine parsed")
    )
    result = await research.public_page_read(
        context(), research.PublicPageInput(url="https://example.org/article")
    )
    assert result.text == ""
    assert result.extraction_method is None


async def test_public_page_rejects_binary_response_after_capture(
    research, captured_source, monkeypatch
):
    captured_source.mime = "application/octet-stream"
    captured_source.body = b"\x00\x01SYNTHETIC"
    monkeypatch.setattr(research, "extract_public_text", lambda *args: pytest.fail("Binary parsed"))
    with pytest.raises(ToolError, match="HTML"):
        await research.public_page_read(
            context(), research.PublicPageInput(url="https://example.org/article")
        )
    assert captured_source.committed


@pytest.mark.parametrize(
    "url", ["http://localhost/feed", "file:///etc/passwd", "https://user:password@example.org/feed"]
)
async def test_feed_input_is_denied_by_real_safe_transport(research, monkeypatch, url):
    async def capture(ctx, *, spec, locator, fetch):
        await fetch()
        pytest.fail("Unsafe input reached capture persistence")

    monkeypatch.setattr(research, "capture", capture)
    with pytest.raises(ToolError, match="public HTTP"):
        await research.rss_read(context(), research.RssReadInput(url=url))


async def test_feedparser_receives_in_memory_stream_without_file_or_network_fallthrough(
    research, captured_source, monkeypatch
):
    import feedparser.api
    import feedparser.http

    state = captured_source
    state.mime = "application/rss+xml"
    state.body = b'<rss version="2.0"><channel><title>SYNTHETIC stream</title></channel></rss>'
    real_parse = research.feedparser.parse

    def parse_stream(source, *args, **kwargs):
        assert state.committed, "Feed content was parsed before capture committed"
        assert hasattr(source, "read"), "Captured content must use the stream-only parser path"
        return real_parse(source, *args, **kwargs)

    def unexpected_io(*args, **kwargs):
        pytest.fail("Feed parsing must not open a file or fetch a URL")

    monkeypatch.setattr(research.feedparser, "parse", parse_stream)
    monkeypatch.setattr(feedparser.api, "open", unexpected_io, raising=False)
    monkeypatch.setattr(feedparser.http, "get", unexpected_io)
    result = await research.rss_read(
        context(), research.RssReadInput(url="https://example.org/feed.xml")
    )
    assert result.title == "SYNTHETIC stream"
    assert result.capture.evidence_code == "E-0042"


@pytest.mark.parametrize(
    "query",
    ["!ddg SYNTHETIC", "SYNTHETIC !images", "SYNTHETIC !!g", "SYNTHETIC :fr", "SYNTHETIC\t!google"],
)
async def test_searxng_query_directives_cannot_override_reviewed_engines(
    research, captured_source, monkeypatch, query
):
    async def unexpected_capture(*args, **kwargs):
        pytest.fail("A SearXNG query directive reached capture")

    monkeypatch.setattr(research, "capture", unexpected_capture)
    with pytest.raises(ToolError) as error:
        await research.surface_search(
            context("https://example.org/search"),
            research.SurfaceSearchInput(query=query, provider="searxng"),
        )
    assert error.value.code == "VALIDATION"
    assert captured_source.calls == []


async def test_duckduckgo_query_bangs_are_preserved(research, captured_source):
    captured_source.mime = "text/html"
    captured_source.body = b'<html><div class="no-results">SYNTHETIC no results</div></html>'
    await research.surface_search(
        context(), research.SurfaceSearchInput(query="SYNTHETIC !bang :word")
    )
    assert captured_source.calls == [
        ("https://html.duckduckgo.com/html/?q=SYNTHETIC+%21bang+%3Aword", "GET")
    ]
