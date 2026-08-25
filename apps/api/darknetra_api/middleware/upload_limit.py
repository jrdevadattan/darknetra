from __future__ import annotations

import re

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MULTIPART_ENVELOPE_MAX_BYTES = 64 * 1024
_UPLOAD_PATH = re.compile(r"^/api/v1/cases/[^/]+/evidence/?$")


class UploadBodyLimitMiddleware:
    """Bound the upload route while ASGI request bytes are still arriving."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or not _UPLOAD_PATH.fullmatch(scope.get("path", ""))
        ):
            await self.app(scope, receive, send)
            return

        runtime_settings = scope["app"].state.runtime_settings
        request_limit = runtime_settings.evidence_upload_max_bytes + MULTIPART_ENVELOPE_MAX_BYTES
        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        raw_content_length = headers.get(b"content-length")
        if raw_content_length is not None:
            try:
                content_length = int(raw_content_length)
            except ValueError:
                await self._reject(scope, send, code="INVALID_CONTENT_LENGTH", status_code=400)
                return
            if content_length < 0:
                await self._reject(scope, send, code="INVALID_CONTENT_LENGTH", status_code=400)
                return
            if content_length > request_limit:
                await self._reject(scope, send, code="UPLOAD_TOO_LARGE", status_code=413)
                return

        received = 0
        overflow = False

        async def limited_receive() -> Message:
            nonlocal overflow, received
            if overflow:
                return {"type": "http.request", "body": b"", "more_body": False}
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                received += len(body)
                if received > request_limit:
                    overflow = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        pending_messages: list[Message] = []

        async def buffered_send(message: Message) -> None:
            pending_messages.append(message)

        await self.app(scope, limited_receive, buffered_send)
        if overflow:
            await self._reject(scope, send, code="UPLOAD_TOO_LARGE", status_code=413)
            return
        for message in pending_messages:
            await send(message)

    @staticmethod
    async def _reject(scope: Scope, send: Send, *, code: str, status_code: int) -> None:
        response = JSONResponse(status_code=status_code, content={"detail": {"code": code}})
        await response(scope, _empty_receive, send)


async def _empty_receive() -> Message:
    return {"type": "http.disconnect"}


__all__ = ["MULTIPART_ENVELOPE_MAX_BYTES", "UploadBodyLimitMiddleware"]
