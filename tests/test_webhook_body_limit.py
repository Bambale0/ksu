from __future__ import annotations

from collections import deque
from typing import Any

import pytest
from starlette.types import Message, Scope

from app.core.webhook_body_limit import WebhookBodyLimitMiddleware


def _scope(*, path: str = "/webhooks/kie", headers: list[tuple[bytes, bytes]] | None = None) -> Scope:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 443),
        "state": {},
    }


async def _run(
    *,
    chunks: list[bytes],
    max_bytes: int,
    headers: list[tuple[bytes, bytes]] | None = None,
    path: str = "/webhooks/kie",
) -> tuple[list[Message], bytes, bool, int]:
    inbound = deque(
        {
            "type": "http.request",
            "body": chunk,
            "more_body": index < len(chunks) - 1,
        }
        for index, chunk in enumerate(chunks)
    )
    receive_calls = 0
    downstream_called = False
    downstream_body = bytearray()
    sent: list[Message] = []

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        if inbound:
            return inbound.popleft()  # type: ignore[return-value]
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    async def downstream(_scope: Scope, downstream_receive: Any, downstream_send: Any) -> None:
        nonlocal downstream_called
        downstream_called = True
        while True:
            message = await downstream_receive()
            if message["type"] != "http.request":
                continue
            downstream_body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await downstream_send({"type": "http.response.start", "status": 204, "headers": []})
        await downstream_send({"type": "http.response.body", "body": b""})

    middleware = WebhookBodyLimitMiddleware(downstream, max_bytes=max_bytes)
    await middleware(_scope(path=path, headers=headers), receive, send)
    return sent, bytes(downstream_body), downstream_called, receive_calls


def _status(messages: list[Message]) -> int:
    start = next(message for message in messages if message["type"] == "http.response.start")
    return int(start["status"])


@pytest.mark.asyncio
async def test_chunked_webhook_body_is_rejected_without_content_length() -> None:
    sent, body, downstream_called, receive_calls = await _run(
        chunks=[b"12345", b"67890", b"x"],
        max_bytes=10,
    )

    assert _status(sent) == 413
    assert not downstream_called
    assert body == b""
    assert receive_calls == 3


@pytest.mark.asyncio
async def test_actual_bytes_override_misleading_small_content_length() -> None:
    sent, _body, downstream_called, _receive_calls = await _run(
        chunks=[b"123456", b"78901"],
        max_bytes=10,
        headers=[(b"content-length", b"1")],
    )

    assert _status(sent) == 413
    assert not downstream_called


@pytest.mark.asyncio
async def test_large_declared_content_length_is_rejected_before_body_read() -> None:
    sent, _body, downstream_called, receive_calls = await _run(
        chunks=[b"not-read"],
        max_bytes=10,
        headers=[(b"content-length", b"11")],
    )

    assert _status(sent) == 413
    assert not downstream_called
    assert receive_calls == 0


@pytest.mark.asyncio
async def test_accepted_webhook_body_is_replayed_unchanged() -> None:
    sent, body, downstream_called, receive_calls = await _run(
        chunks=[b'{"task":', b'"abc"}'],
        max_bytes=32,
    )

    assert _status(sent) == 204
    assert downstream_called
    assert body == b'{"task":"abc"}'
    assert receive_calls == 2


@pytest.mark.asyncio
async def test_non_webhook_routes_are_not_prebuffered_by_limiter() -> None:
    sent, body, downstream_called, receive_calls = await _run(
        chunks=[b"12345678901"],
        max_bytes=10,
        path="/api/v1/generations",
    )

    assert _status(sent) == 204
    assert downstream_called
    assert body == b"12345678901"
    assert receive_calls == 1
