"""SYNTHETIC public-reader contract tests; no live requests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from darknetra.capture.fetcher import Fetched
from darknetra.capture.gate import CaptureResult
from darknetra.tools.contracts import ToolError


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.1/",
        "http://2130706433/",
        "http://internal/",
        "https://user:password@example.test/",
        "http://abc.onion/",
    ],
)
async def test_reader_rejects_nonpublic_target_before_capture(url, monkeypatch):
    from darknetra.tools.impl import agent_reach as adapter

    async def forbidden(*args, **kwargs):
        pytest.fail("Invalid target reached capture")

    monkeypatch.setattr(adapter, "capture", forbidden)
    with pytest.raises(ToolError) as exc:
        await adapter.agent_reach_read(SimpleNamespace(), adapter.ReaderInput(url=url))
    assert exc.value.code == "POLICY_DENIED"


@pytest.mark.parametrize("quarantined", [False, True])
async def test_reader_capture_precedes_upstream_check(monkeypatch, quarantined):
    from darknetra.tools.impl import agent_reach as adapter

    events = []
    evidence = CaptureResult(
        evidence_code="E-0001",
        evidence_id=uuid4(),
        duplicate=False,
        excerpt="SYNTHETIC captured excerpt",
        source_class="OSINT_SURFACE",
        captured_at=datetime.now(UTC),
        quarantined=quarantined,
    )

    async def fetch(self, url):
        events.append("fetch")
        return Fetched(
            b"SYNTHETIC public representation", "text/plain", url, 200, {}, datetime.now(UTC)
        )

    async def capture(ctx, *, spec, locator, fetch):
        await fetch()
        events.append("persist")
        return evidence

    def check(body):
        assert events == ["fetch", "persist"]
        events.append("check")
        return False

    monkeypatch.setattr(adapter.SafeHttp, "fetch", fetch)
    monkeypatch.setattr(adapter, "capture", capture)
    monkeypatch.setattr(adapter, "_is_antibot_page", check)
    result = await adapter.agent_reach_read(
        SimpleNamespace(), adapter.ReaderInput(url="https://example.test/")
    )
    assert result.capture.evidence_id == evidence.evidence_id
    assert result.representation == "JINA_READER"
    assert result.origin_verified is False
    assert events == (["fetch", "persist"] if quarantined else ["fetch", "persist", "check"])


async def test_reader_rejects_captured_challenge(monkeypatch):
    from darknetra.tools.impl import agent_reach as adapter

    persisted = False

    async def fetch(self, url):
        return Fetched(
            b"Title: Just a moment...\nWarning: requiring CAPTCHA",
            "text/plain",
            url,
            200,
            {},
            datetime.now(UTC),
        )

    async def capture(ctx, *, spec, locator, fetch):
        nonlocal persisted
        await fetch()
        persisted = True
        return CaptureResult(
            evidence_code="E-0001",
            evidence_id=uuid4(),
            duplicate=False,
            excerpt="challenge",
            source_class="OSINT_SURFACE",
            captured_at=datetime.now(UTC),
            quarantined=False,
        )

    monkeypatch.setattr(adapter.SafeHttp, "fetch", fetch)
    monkeypatch.setattr(adapter, "capture", capture)
    with pytest.raises(ToolError) as exc:
        await adapter.agent_reach_read(
            SimpleNamespace(), adapter.ReaderInput(url="https://example.test/")
        )
    assert exc.value.code == "UNAVAILABLE"
    assert persisted
