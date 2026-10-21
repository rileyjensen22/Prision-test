"""Security headers and request-size limit, as plain ASGI middleware."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"cache-control": b"no-store",
    b"referrer-policy": b"no-referrer",
    b"x-frame-options": b"DENY",
    b"content-security-policy": b"default-src 'none'; frame-ancestors 'none'",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=()",
}
# FastAPI's own docs pages load scripts, so they are not given the API's strict policy.
DOCS_PATHS = {"/docs", "/redoc", "/docs/oauth2-redirect"}


class SecurityHeaders:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in DOCS_PATHS:
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message["headers"] if k.lower() not in API_HEADERS]
                headers.extend(API_HEADERS.items())
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodyLimit:
    """Rejects request bodies over `max_bytes` (413), whether or not they declare a length."""

    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        seen = 0
        too_big = False

        async def limited_receive() -> Message:
            nonlocal seen, too_big
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    too_big = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        started = False

        async def guarded_send(message: Message) -> None:
            nonlocal started
            if too_big and not started:
                started = True
                await self._reject(send)
                return
            if too_big:
                return
            started = started or message["type"] == "http.response.start"
            await send(message)

        await self.app(scope, limited_receive, guarded_send)

    async def _reject(self, send: Send) -> None:
        body = b'{"detail":"request body too large"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
