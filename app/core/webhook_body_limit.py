from __future__ import annotations

from collections.abc import Sequence

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings


class WebhookBodyLimitMiddleware:
    """Bound public webhook request bodies before FastAPI parses them.

    Provider signatures generally require fields from the request body, so several
    webhook routes cannot authenticate a request until after parsing JSON/form data.
    Limiting only ``Content-Length`` is insufficient because HTTP/1.1 chunked bodies
    can omit it. This middleware consumes at most the configured number of actual
    ASGI body bytes, rejects oversized requests, then replays accepted chunks to the
    normal application stack.
    """

    def __init__(self, app: ASGIApp, max_bytes: int | None = None) -> None:
        self.app = app
        self.max_bytes = int(max_bytes or settings.webhook_body_max_bytes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._is_webhook_path(str(scope.get("path") or "")):
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope.get("headers") or [])
        if content_length is not None and content_length > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                buffered.append(message)
                continue

            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(buffered):
                message = buffered[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, send)

    @staticmethod
    def _is_webhook_path(path: str) -> bool:
        return path == "/webhooks" or path.startswith("/webhooks/")

    @staticmethod
    def _content_length(headers: Sequence[tuple[bytes, bytes]]) -> int | None:
        for raw_name, raw_value in headers:
            if raw_name.lower() != b"content-length":
                continue
            try:
                value = int(raw_value.decode("ascii").strip())
            except (UnicodeDecodeError, ValueError):
                return None
            return max(0, value)
        return None

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "Webhook payload is too large"},
        )
        await response(scope, receive, send)
