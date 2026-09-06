"""SYNTHETIC saved index inputs; no external or onion requests are made."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from darknetra.capture.fetcher import Fetched
from darknetra.capture.gate import CaptureResult
from darknetra.tools.contracts import ToolError

HOST = "a" * 56 + ".onion"  # SYNTHETIC shape-only locator, never contacted.
URL = f"http://{HOST}/synthetic"


def index_html(anchors):
    return (
        '<div id="ahmiaResultsPage"><ol class="searchResults"><li class="result"><h4>'
        + anchors
        + "</h4></li></ol></div>"
    ).encode()


def test_parser_preserves_unicode_first_hit_and_deduplicates_slash():
    from darknetra.integrations.robin import parse_index

    html = index_html(
        f'<a href="{URL}/">SYNTHETIC ਪੰਜਾਬੀ समाचार</a>'
        f'<a href="{URL}">SYNTHETIC duplicate</a>'
        f'<a href="{URL}/second">SYNTHETIC second</a>'
    )
    hits = parse_index(html, limit=5)
    assert [(hit.title, hit.url) for hit in hits] == [
        ("SYNTHETIC ਪੰਜਾਬੀ समाचार", URL + "/"),
        ("SYNTHETIC second", URL + "/second"),
    ]


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "http://localhost/",
        "http://127.0.0.1/",
        "http://short.onion/",
        f"http://{HOST}.example.test/",
        f"http://user:password@{HOST}/",
        f"http://{HOST}:8080/",
        f"http://{HOST}/%0aheader",
        f"http://{HOST}\\evil/",
        f"https://example.test/?next={URL}",
        f"/not-a-search-redirect?redirect_url={URL}",
        f"{URL}/search?q=synthetic",
    ],
)
def test_parser_rejects_adversarial_or_non_target_links(href):
    from darknetra.integrations.robin import parse_index

    # A valid sibling remains visible; rejected targets never appear as hits.
    html = index_html(
        f'<a href="{href}">SYNTHETIC invalid title</a><a href="{URL}">SYNTHETIC valid</a>'
    )
    assert [hit.title for hit in parse_index(html)] == ["SYNTHETIC valid"]


def test_parser_accepts_only_known_index_redirect_wrapper():
    from darknetra.integrations.robin import parse_index

    html = index_html(
        f'<a href="/search/redirect?redirect_url=http%3A%2F%2F{HOST}%2Fsynthetic">'
        "SYNTHETIC result</a>"
    )
    assert parse_index(html)[0].url == URL


def test_parser_caps_results_titles_and_input():
    from darknetra.integrations.robin import parse_index

    html = "".join(f'<a href="{URL}/{i}">{"SYNTHETIC " * 100}</a>' for i in range(20))
    hits = parse_index(index_html(html), limit=2)
    assert len(hits) == 2
    assert all(len(hit.title) <= 300 for hit in hits)
    with pytest.raises(ValueError):
        parse_index(b"x" * 1_000_001)
    with pytest.raises(ValueError):
        parse_index(b"", limit=11)


def test_query_rejects_unbounded_or_model_supplied_case():
    from pydantic import ValidationError

    from darknetra.tools.impl.robin import RobinSearchInput

    for args in ({"query": " "}, {"query": "x", "limit": 11}, {"query": "x", "case_id": "x"}):
        with pytest.raises(ValidationError):
            RobinSearchInput.model_validate(args)


def captured_result(*, quarantined=False):
    return CaptureResult(
        evidence_code="E-0042",
        evidence_id=uuid4(),
        duplicate=False,
        excerpt="SYNTHETIC index excerpt",
        source_class="OSINT_DARK",
        captured_at=datetime.now(UTC),
        quarantined=quarantined,
    )


async def test_search_captures_before_parser_and_returns_parent_evidence(monkeypatch):
    from darknetra.tools.impl import robin
    from darknetra.tools.registry import REGISTRY

    events = []
    capture_result = captured_result()
    ctx = SimpleNamespace(case_id=uuid4())
    monkeypatch.setitem(REGISTRY, "robin_search", SimpleNamespace(name="robin_search"))

    async def fetch(self, url):
        events.append("fetch")
        assert url == "https://ahmia.fi/search/?q=SYNTHETIC+%26+news"
        return Fetched(
            index_html(f'<a href="{URL}">SYNTHETIC index title</a>'),
            "text/html",
            url,
            200,
            {},
            datetime.now(UTC),
        )

    async def capture(context, *, spec, locator, fetch):
        assert context is ctx
        assert spec.name == "robin_search"
        assert locator.startswith("https://ahmia.fi/search/?")
        events.append("policy")
        await fetch()
        events.append("persisted")
        return capture_result

    real_parse = robin.parse_index

    def parse(data, *, limit):
        assert events == ["policy", "fetch", "persisted"]
        events.append("parse")
        return real_parse(data, limit=limit)

    monkeypatch.setattr(robin.SafeHttp, "fetch", fetch)
    monkeypatch.setattr(robin, "capture", capture)
    monkeypatch.setattr(robin, "parse_index", parse)
    result = await robin.robin_search(ctx, robin.RobinSearchInput(query="SYNTHETIC & news"))
    assert result.evidence_id == capture_result.evidence_id
    assert result.hits[0].evidence_code == "E-0042"
    assert result.hits[0].evidence_id == capture_result.evidence_id
    assert result.hits[0].target_fetched is False
    assert result.hits[0].observation_kind == "INDEX_ENTRY"
    assert result.hits[0].excerpt == "SYNTHETIC index title"
    assert events == ["policy", "fetch", "persisted", "parse"]


@pytest.mark.parametrize(
    "code", ["NETWORK_REQUIRED", "POLICY_DENIED", "RATE_LIMITED", "UNAVAILABLE"]
)
async def test_search_preserves_gate_failures_without_parsing(monkeypatch, code):
    from darknetra.tools.impl import robin
    from darknetra.tools.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "robin_search", SimpleNamespace(name="robin_search"))

    async def denied(*args, **kwargs):
        raise ToolError(code, "SYNTHETIC source failure")

    def forbidden_parse(*args, **kwargs):
        pytest.fail("Parser ran after denied/failed capture")

    monkeypatch.setattr(robin, "capture", denied)
    monkeypatch.setattr(robin, "parse_index", forbidden_parse)
    with pytest.raises(ToolError) as error:
        await robin.robin_search(SimpleNamespace(), robin.RobinSearchInput(query="SYNTHETIC"))
    assert error.value.code == code


async def test_quarantined_capture_never_reaches_parser(monkeypatch):
    from darknetra.tools.impl import robin
    from darknetra.tools.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "robin_search", SimpleNamespace(name="robin_search"))

    async def quarantined(*args, **kwargs):
        return captured_result(quarantined=True)

    def forbidden_parse(*args, **kwargs):
        pytest.fail("Quarantined bytes reached parser")

    monkeypatch.setattr(robin, "capture", quarantined)
    monkeypatch.setattr(robin, "parse_index", forbidden_parse)
    result = await robin.robin_search(SimpleNamespace(), robin.RobinSearchInput(query="SYNTHETIC"))
    assert result.hits == []
    assert result.quarantined is True


@pytest.mark.parametrize(
    ("mime", "data", "code"),
    [("application/json", b"{}", "UNAVAILABLE"), ("text/html", b"x" * 1_000_001, "VALIDATION")],
    ids=["unsupported-mime", "oversized-html"],
)
async def test_captured_unsupported_or_oversized_index_has_explicit_error(
    monkeypatch, mime, data, code
):
    from darknetra.tools.impl import robin
    from darknetra.tools.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "robin_search", SimpleNamespace(name="robin_search"))
    persisted = False

    async def fetch(self, url):
        return Fetched(data, mime, url, 200, {}, datetime.now(UTC))

    async def capture(context, *, spec, locator, fetch):
        nonlocal persisted
        await fetch()
        persisted = True
        return captured_result()

    monkeypatch.setattr(robin.SafeHttp, "fetch", fetch)
    monkeypatch.setattr(robin, "capture", capture)
    with pytest.raises(ToolError) as error:
        await robin.robin_search(SimpleNamespace(), robin.RobinSearchInput(query="SYNTHETIC"))
    assert error.value.code == code
    assert persisted


@pytest.mark.parametrize(
    "data",
    [
        b'<html><title>Just a moment...</title><form id="challenge-form">SYNTHETIC CAPTCHA</form></html>',
        b"<html><h1>SYNTHETIC maintenance outage</h1></html>",
        b'<div id="ahmiaResultsPage"><ol class="searchResults"></ol></div>',
        b'<p id="noResults">SYNTHETIC lookalike without Ahmia page structure</p>',
        index_html('<a href="http://short.onion/">SYNTHETIC malformed index target</a>'),
    ],
    ids=["challenge", "outage", "empty-container", "unknown-layout", "unparseable-results"],
)
async def test_unrecognized_index_is_unavailable_after_capture(monkeypatch, data):
    from darknetra.tools.impl import robin

    events = []

    async def fetch(self, url):
        events.append("fetch")
        return Fetched(data, "text/html", url, 200, {}, datetime.now(UTC))

    async def capture(context, *, spec, locator, fetch):
        await fetch()
        events.append("persisted")
        return captured_result()

    real_parse = robin.parse_index

    def parse(data, *, limit):
        assert events == ["fetch", "persisted"]
        events.append("parse")
        return real_parse(data, limit=limit)

    monkeypatch.setattr(robin.SafeHttp, "fetch", fetch)
    monkeypatch.setattr(robin, "capture", capture)
    monkeypatch.setattr(robin, "parse_index", parse)
    with pytest.raises(ToolError) as error:
        await robin.robin_search(SimpleNamespace(), robin.RobinSearchInput(query="SYNTHETIC"))
    assert error.value.code == "UNAVAILABLE"
    assert events == ["fetch", "persisted", "parse"]


def test_explicit_provider_no_results_is_only_clean_empty():
    from darknetra.integrations.robin import parse_index

    assert (
        parse_index(b'<div id="ahmiaResultsPage"><p id="noResults">SYNTHETIC no results</p></div>')
        == []
    )
