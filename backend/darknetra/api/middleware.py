"""Reject oversized request streams before multipart parsing buffers them."""

from starlette.responses import JSONResponse

from darknetra.errors import TooLarge


class RequestSizeLimit:
    def __init__(self, app, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = self.max_bytes + 1
        if length > self.max_bytes:
            response = JSONResponse(
                {
                    "error": {
                        "code": "VALIDATION",
                        "message": "Request exceeds the upload limit",
                        "detail": {},
                        "request_id": scope.get("state", {}).get("request_id"),
                    }
                },
                status_code=413,
            )
            return await response(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    raise TooLarge("Request exceeds the upload limit")
            return message

        await self.app(scope, bounded_receive, send)
