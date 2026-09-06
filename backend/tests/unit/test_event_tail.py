"""SYNTHETIC commit interleaving: terminal status cannot hide the event tail."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4


async def test_terminal_commit_between_reads_does_not_drop_tail(monkeypatch):
    from darknetra.agent import events

    committed = False
    row = SimpleNamespace(seq=1, type="run.finished", data={"status": "DONE"}, at=datetime.now(UTC))

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def scalar(self, query):
            return SimpleNamespace(status="DONE" if committed else "RUNNING")

        async def scalars(self, query):
            nonlocal committed
            current = committed
            committed = True
            return SimpleNamespace(all=lambda: [row] if current else [])

    async def no_wait(*args):
        pass

    monkeypatch.setattr(events.asyncio, "sleep", no_wait)
    streamed = [item async for item in events.stream(Session, uuid4(), uuid4())]
    assert [item["event"] for item in streamed] == ["run.finished"]
