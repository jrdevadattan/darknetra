from types import SimpleNamespace
from uuid import uuid4

import pytest

from darknetra.monitor import adapters
from darknetra.tools.contracts import ToolResult


@pytest.mark.parametrize(
    "hits",
    [[], [{"title": "Unrelated", "excerpt": "Nothing relevant", "url": "https://example.org/"}]],
)
async def test_monitor_never_counts_query_echo_or_unrelated_index(monkeypatch, hits):
    async def invoke(ctx, name, args):
        assert name == "surface_search"
        return ToolResult(
            ok=True,
            data={
                "capture": {"evidence_id": str(uuid4())},
                "hits": hits,
                "excerpt": "SYNTHETIC_WATCH query echo",
            },
        )

    monkeypatch.setattr(adapters, "invoke", invoke)
    case = SimpleNamespace(id=uuid4())
    item = SimpleNamespace(value="SYNTHETIC_WATCH", variants=["SYNTHETIC_WATCH"])
    result = await adapters.collect(None, case, item, "web_search", SimpleNamespace(settings=None))
    assert result == []
