import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 1024 * 1024
_MAX_TRACKED_CLIENTS = 10_000


class _BodyTooLargeError(Exception):
    """Raised while reading a body without Content-Length that exceeds the limit."""


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > self.max_bytes:
            response = JSONResponse({"detail": "Request body too large"}, status_code=413)
            await response(scope, receive, send)
            return

        seen = 0

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        await self.app(scope, limited_receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, production: bool) -> None:
        self.app = app
        self.headers = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
        ]
        if production:
            self.headers += [
                (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
                (b"strict-transport-security", b"max-age=31536000"),
            ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *self.headers]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class SlidingWindowLimiter:
    """Per-client limit held in this process; enough while the app runs as one process."""

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self.clock()
        with self._lock:
            if len(self._hits) > _MAX_TRACKED_CLIENTS:
                self._drop_idle_clients(now)
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def _drop_idle_clients(self, now: float) -> None:
        idle = [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window_seconds]
        for key in idle:
            del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_limiters: dict[str, SlidingWindowLimiter] = {}


def rate_limit(name: str, limit: int) -> Callable[[Request], Any]:
    """Build a route dependency that answers 429 after `limit` calls per minute per client."""
    limiter = _limiters.setdefault(name, SlidingWindowLimiter(limit))

    def check(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": "60"},
            )

    return check


def reset_rate_limits() -> None:
    for limiter in _limiters.values():
        limiter.reset()
