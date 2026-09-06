"""In-process jobs; each factory owns its database session and transaction."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobStatus:
    id: str
    name: str
    status: str
    error: str | None = None
    finished_at: datetime | None = None


class JobRunner(Protocol):
    async def submit(
        self, name: str, coro_factory: Callable[[], Awaitable[None]], *, key: str | None = None
    ) -> str: ...

    async def status(self, job_id: str) -> JobStatus: ...


class InProcessRunner:
    def __init__(self, max_workers: int = 4) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self._semaphore = asyncio.Semaphore(max_workers)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._keys: dict[str, str] = {}
        self._statuses: dict[str, JobStatus] = {}
        self._closing = False

    async def submit(
        self, name: str, coro_factory: Callable[[], Awaitable[None]], *, key: str | None = None
    ) -> str:
        if self._closing:
            raise RuntimeError("Job runner is shutting down")
        if key and key in self._keys:
            return self._keys[key]
        job_id = str(uuid4())
        self._statuses[job_id] = JobStatus(job_id, name, "QUEUED")
        if key:
            self._keys[key] = job_id

        async def run() -> None:
            try:
                async with self._semaphore:
                    self._statuses[job_id] = JobStatus(job_id, name, "RUNNING")
                    await coro_factory()
                self._statuses[job_id] = JobStatus(
                    job_id, name, "DONE", finished_at=datetime.now(UTC)
                )
            except asyncio.CancelledError:
                self._statuses[job_id] = JobStatus(
                    job_id, name, "CANCELLED", finished_at=datetime.now(UTC)
                )
            except Exception as exc:
                # Exception strings may contain uploaded content, URLs or provider secrets.
                error = type(exc).__name__
                log.error("job_failed name=%s id=%s error_type=%s", name, job_id, error)
                self._statuses[job_id] = JobStatus(
                    job_id, name, "FAILED", error=error, finished_at=datetime.now(UTC)
                )
            finally:
                if key and self._keys.get(key) == job_id:
                    self._keys.pop(key, None)

        task = asyncio.create_task(run(), name=f"darknetra:{name}:{job_id}")
        self._tasks[job_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(job_id, None))
        return job_id

    async def status(self, job_id: str) -> JobStatus:
        return self._statuses[job_id]

    async def cancel(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        current = self._statuses.get(job_id)
        if current and current.status in {"QUEUED", "RUNNING"}:
            self._statuses[job_id] = JobStatus(
                job_id, current.name, "CANCELLED", finished_at=datetime.now(UTC)
            )
        for key in [key for key, value in self._keys.items() if value == job_id]:
            self._keys.pop(key, None)

    async def wait_all(self) -> None:
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks.values()), return_exceptions=True)

    async def shutdown(self) -> None:
        self._closing = True
        for task in tuple(self._tasks.values()):
            task.cancel()
        await self.wait_all()
        self._keys.clear()
