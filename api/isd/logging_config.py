"""Structured (JSON) logs: one line per request, and nothing sensitive in it.

A request line has the method, the route *template* (never the real path or query string, which can
hold ids), the status, how long it took, who kind of caller it was, the address, and a request id
that is also sent back in `X-Request-ID`. Tokens, headers, bodies and names are never logged.
"""

import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_LOGGER = "isd.request"
_STD = {"name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info",
        "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message", "taskName"}  # fmt: skip


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        out.update({k: v for k, v in record.__dict__.items() if k not in _STD})
        if record.exc_info and record.exc_info[0] is not None:
            out["error_type"] = record.exc_info[0].__name__  # the type only: messages can hold data
        return json.dumps(out, default=str)


def configure_logging(level: str | None = None) -> None:
    """Idempotent: installs one JSON handler on the `isd` loggers."""
    root = logging.getLogger("isd")
    root.setLevel((level or os.environ.get("LOG_LEVEL", "INFO")).upper())
    if not any(getattr(h, "_isd_json", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._isd_json = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.propagate = False


def _caller_kind(headers: dict[bytes, bytes]) -> str:
    if b"x-device-token" in headers:
        return "device"
    if b"authorization" in headers:
        return "staff"
    return "anonymous"


class RequestLog:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.log = logging.getLogger(REQUEST_LOGGER)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex[:16]
        started = time.perf_counter()
        status = 500

        async def send_wrapped(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [*message["headers"], (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapped)
        finally:
            route = scope.get("route")
            client = scope.get("client")
            self.log.log(
                logging.ERROR if status >= 500 else logging.INFO,
                "request",
                extra={
                    "request_id": request_id,
                    "method": scope["method"],
                    "route": getattr(route, "path", "unmatched"),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "caller": _caller_kind(dict(scope["headers"])),
                    "ip": client[0] if client else None,
                },
            )
