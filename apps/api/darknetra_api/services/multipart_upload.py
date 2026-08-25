from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import cast

import anyio
from fastapi import Request
from pydantic import ValidationError
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import MultipartParser, parse_options_header

from darknetra_api.middleware.upload_limit import MULTIPART_ENVELOPE_MAX_BYTES
from darknetra_api.policy.ingestion import (
    DEFAULT_PREFIX_BYTES,
    EvidenceSourceMetadata,
    PreservedUpload,
    preserve_upload_after_envelope,
)
from darknetra_api.storage.base import ObjectStore

_PARSER_CHUNK_BYTES = 64 * 1024
_QUEUE_DEPTH = 2
_MAX_HEADERS = 8
_MAX_HEADER_BYTES = 4224
_MAX_BOUNDARY_BYTES = 256


class InvalidMultipartError(ValueError):
    """Stable, intentionally message-free multipart contract failure."""


class _MultipartStreamAborted(Exception):
    pass


class _ContractError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class _FileStart:
    filename: str
    content_type: str | None


@dataclass(frozen=True, slots=True)
class _FileData:
    data: bytes


class _FileEnd:
    pass


_FILE_END = _FileEnd()
_QUEUE_EOF = object()
_QUEUE_ABORT = object()


class _EnvelopeGate:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._metadata: EvidenceSourceMetadata | None = None
        self._accepted = False

    def accept(self, metadata: EvidenceSourceMetadata) -> None:
        self._metadata = metadata
        self._accepted = True
        self._event.set()

    def reject(self) -> None:
        self._event.set()

    def wait(self) -> EvidenceSourceMetadata:
        self._event.wait()
        if not self._accepted or self._metadata is None:
            raise _MultipartStreamAborted
        return self._metadata


class _AsyncQueueBinaryStream:
    """Blocking BinaryIO facade over a bounded event-loop queue."""

    def __init__(
        self,
        queue: asyncio.Queue[bytes | object],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._queue = queue
        self._loop = loop
        self._buffer = bytearray()
        self._eof = False

    def read(self, size: int = -1) -> bytes:
        if size <= 0:
            raise ValueError("stream reads require a positive size")
        if self._buffer:
            return self._take(size)
        if self._eof:
            return b""
        item = asyncio.run_coroutine_threadsafe(self._queue.get(), self._loop).result()
        if item is _QUEUE_ABORT:
            raise _MultipartStreamAborted
        if item is _QUEUE_EOF:
            self._eof = True
            return b""
        self._buffer.extend(cast(bytes, item))
        return self._take(size)

    def _take(self, size: int) -> bytes:
        count = min(size, len(self._buffer))
        value = bytes(self._buffer[:count])
        del self._buffer[:count]
        return value

    def readable(self) -> bool:
        return True


class _MultipartCallbacks:
    def __init__(self) -> None:
        self.events: list[_FileStart | _FileData | _FileEnd] = []
        self.metadata = bytearray()
        self.metadata_parts = 0
        self.file_parts = 0
        self.finished = False
        self._header_name = bytearray()
        self._header_value = bytearray()
        self._headers: dict[bytes, bytes] = {}
        self._part_kind: str | None = None

    def callbacks(self) -> dict[str, Callable[..., None]]:
        return {
            "on_part_begin": self.on_part_begin,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_end": self.on_end,
        }

    def on_part_begin(self) -> None:
        self._header_name.clear()
        self._header_value.clear()
        self._headers.clear()
        self._part_kind = None

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name.extend(data[start:end])

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value.extend(data[start:end])

    def on_header_end(self) -> None:
        name = bytes(self._header_name).lower()
        if not name or name in self._headers:
            raise _ContractError
        self._headers[name] = bytes(self._header_value)
        self._header_name.clear()
        self._header_value.clear()

    def on_headers_finished(self) -> None:
        raw_disposition = self._headers.get(b"content-disposition")
        if raw_disposition is None:
            raise _ContractError
        disposition, options = parse_options_header(raw_disposition)
        if disposition != b"form-data":
            raise _ContractError
        name = options.get(b"name")
        if name == b"metadata":
            if b"filename" in options or self.metadata_parts:
                raise _ContractError
            self.metadata_parts = 1
            self._part_kind = "metadata"
            return
        if name == b"file":
            raw_filename = options.get(b"filename")
            if raw_filename is None or self.file_parts:
                raise _ContractError
            self.file_parts = 1
            self._part_kind = "file"
            filename = _decode_filename(raw_filename)
            raw_content_type = self._headers.get(b"content-type")
            content_type = _decode_content_type(raw_content_type)
            self.events.append(_FileStart(filename, content_type))
            return
        raise _ContractError

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        value = data[start:end]
        if self._part_kind == "metadata":
            if len(self.metadata) + len(value) > MULTIPART_ENVELOPE_MAX_BYTES:
                raise _ContractError
            self.metadata.extend(value)
            return
        if self._part_kind == "file":
            if value:
                self.events.append(_FileData(bytes(value)))
            return
        raise _ContractError

    def on_part_end(self) -> None:
        if self._part_kind == "file":
            self.events.append(_FILE_END)
        if self._part_kind is None:
            raise _ContractError

    def on_end(self) -> None:
        self.finished = True

    def validate_contract(self) -> EvidenceSourceMetadata:
        if not self.finished or self.file_parts != 1 or self.metadata_parts != 1:
            raise _ContractError
        return EvidenceSourceMetadata.model_validate_json(bytes(self.metadata))


def _decode_filename(value: bytes) -> str:
    try:
        decoded = value.decode("utf-8")
    except UnicodeDecodeError:
        decoded = value.decode("latin-1")
    if not decoded or "\x00" in decoded:
        raise _ContractError
    return decoded


def _decode_content_type(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        return value.decode("ascii")
    except UnicodeDecodeError as exc:
        raise _ContractError from exc


def _preserve_and_signal(
    *,
    started: threading.Event,
    finished: threading.Event,
    stream: _AsyncQueueBinaryStream,
    object_store: ObjectStore,
    gate: _EnvelopeGate,
    filename: str,
    declared_content_type: str | None,
    max_bytes: int,
) -> tuple[EvidenceSourceMetadata, PreservedUpload]:
    started.set()
    try:
        return preserve_upload_after_envelope(
            stream=stream,
            object_store=object_store,
            metadata_provider=gate.wait,
            filename=filename,
            declared_content_type=declared_content_type,
            max_bytes=max_bytes,
            prefix_bytes=DEFAULT_PREFIX_BYTES,
        )
    finally:
        finished.set()


def _boundary(request: Request) -> bytes:
    content_type = request.headers.get("content-type")
    if content_type is None:
        raise InvalidMultipartError
    try:
        media_type, options = parse_options_header(content_type)
    except (FormParserError, ValueError) as exc:
        raise InvalidMultipartError from exc
    boundary = options.get(b"boundary")
    if media_type != b"multipart/form-data" or boundary is None:
        raise InvalidMultipartError
    if not boundary or len(boundary) > _MAX_BOUNDARY_BYTES:
        raise InvalidMultipartError
    return boundary


async def _put_with_backpressure(
    queue: asyncio.Queue[bytes | object],
    item: bytes | object,
    worker: asyncio.Task[tuple[EvidenceSourceMetadata, PreservedUpload]],
) -> None:
    put = asyncio.create_task(queue.put(item))
    try:
        done, _ = await asyncio.wait({put, worker}, return_when=asyncio.FIRST_COMPLETED)
        if worker in done:
            if not put.done():
                put.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await put
            worker.result()
        else:
            await put
    except BaseException:
        if not put.done():
            put.cancel()
        raise


def _abort_queue(queue: asyncio.Queue[bytes | object]) -> None:
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    queue.put_nowait(_QUEUE_ABORT)


async def _finish_failed_worker(
    *,
    gate: _EnvelopeGate,
    queue: asyncio.Queue[bytes | object] | None,
    worker: asyncio.Task[tuple[EvidenceSourceMetadata, PreservedUpload]] | None,
    worker_started: threading.Event | None,
    worker_finished: threading.Event | None,
) -> None:
    gate.reject()
    if queue is not None:
        _abort_queue(queue)
    if worker_finished is not None:
        current = asyncio.current_task()
        while not worker_finished.is_set():
            if (
                worker is not None
                and worker.cancelled()
                and not (worker_started is not None and worker_started.is_set())
            ):
                break
            try:
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                if current is not None:
                    current.uncancel()
    if worker is not None and not worker.cancelled():
        with contextlib.suppress(BaseException):
            await asyncio.shield(worker)


async def stream_multipart_upload(
    request: Request,
    *,
    object_store: ObjectStore,
    max_bytes: int,
) -> tuple[EvidenceSourceMetadata, PreservedUpload]:
    """Parse one upload with bounded memory and direct object-store staging."""

    boundary = _boundary(request)
    callbacks = _MultipartCallbacks()
    try:
        parser = MultipartParser(
            boundary,
            callbacks.callbacks(),
            max_header_count=_MAX_HEADERS,
            max_header_size=_MAX_HEADER_BYTES,
        )
    except (FormParserError, ValueError) as exc:
        raise InvalidMultipartError from exc

    loop = asyncio.get_running_loop()
    gate = _EnvelopeGate()
    queue: asyncio.Queue[bytes | object] | None = None
    worker: asyncio.Task[tuple[EvidenceSourceMetadata, PreservedUpload]] | None = None
    worker_started: threading.Event | None = None
    worker_finished: threading.Event | None = None
    file_ended = False

    async def process_events() -> None:
        nonlocal queue, worker, worker_started, worker_finished, file_ended
        events, callbacks.events = callbacks.events, []
        for event in events:
            if isinstance(event, _FileStart):
                if worker is not None:
                    raise _ContractError
                queue = asyncio.Queue(maxsize=_QUEUE_DEPTH)
                stream = _AsyncQueueBinaryStream(queue, loop)
                worker_started = threading.Event()
                worker_finished = threading.Event()
                worker = asyncio.create_task(
                    anyio.to_thread.run_sync(
                        partial(
                            _preserve_and_signal,
                            started=worker_started,
                            finished=worker_finished,
                            stream=stream,
                            object_store=object_store,
                            gate=gate,
                            filename=event.filename,
                            declared_content_type=event.content_type,
                            max_bytes=max_bytes,
                        )
                    )
                )
            elif isinstance(event, _FileData):
                if queue is None or worker is None or file_ended:
                    raise _ContractError
                await _put_with_backpressure(queue, event.data, worker)
            else:
                if queue is None or worker is None or file_ended:
                    raise _ContractError
                file_ended = True
                await _put_with_backpressure(queue, _QUEUE_EOF, worker)

    try:
        async for request_chunk in request.stream():
            for offset in range(0, len(request_chunk), _PARSER_CHUNK_BYTES):
                parser.write(request_chunk[offset : offset + _PARSER_CHUNK_BYTES])
                await process_events()
                if worker is not None and worker.done():
                    worker.result()
        parser.finalize()
        await process_events()
        metadata = callbacks.validate_contract()
        if worker is None or queue is None or not file_ended:
            raise _ContractError
        gate.accept(metadata)
        return await worker
    except ValidationError:
        await _finish_failed_worker(
            gate=gate,
            queue=queue,
            worker=worker,
            worker_started=worker_started,
            worker_finished=worker_finished,
        )
        raise
    except (FormParserError, _ContractError, InvalidMultipartError) as exc:
        await _finish_failed_worker(
            gate=gate,
            queue=queue,
            worker=worker,
            worker_started=worker_started,
            worker_finished=worker_finished,
        )
        raise InvalidMultipartError from exc
    except BaseException:
        await _finish_failed_worker(
            gate=gate,
            queue=queue,
            worker=worker,
            worker_started=worker_started,
            worker_finished=worker_finished,
        )
        raise


__all__ = ["InvalidMultipartError", "stream_multipart_upload"]
