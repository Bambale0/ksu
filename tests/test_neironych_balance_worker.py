"""Worker-loop regressions using fake I/O only; never call Telegram or a database."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.core.observability import request_id_var
from app.workers import notifications as worker


class _DeliveryProcessed(Exception):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["hung", 401, 403, 404, 429, 503, "transport"])
async def test_balance_poll_failure_cannot_stop_ordinary_delivery(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, failure: object,
) -> None:
    closed: list[str] = []
    processed: list[object] = []
    poll_request_ids: list[str | None] = []
    delivery_id = uuid4()

    async def close_redis():
        closed.append("redis")

    async def close_bot():
        closed.append("bot")

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def commit(self):
            pass

    async def heartbeat(_):
        pass

    async def poll():
        poll_request_ids.append(request_id_var.get())
        if failure == "hung":
            await asyncio.Event().wait()
        request = httpx.Request("GET", "https://example.test/v1/balance")
        if isinstance(failure, int):
            response = httpx.Response(failure, request=request)
            raise httpx.HTTPStatusError(
                "sensitive-body-must-not-be-logged", request=request, response=response,
            )
        raise httpx.ConnectError("secret-url-must-not-be-logged", request=request)

    async def claim(_):
        return [SimpleNamespace(id=delivery_id)]

    async def deliver(bot, claimed_id):
        processed.append(claimed_id)
        raise _DeliveryProcessed

    monkeypatch.setattr(worker.settings, "bot_token", "fake-not-used")
    monkeypatch.setattr(worker, "_BALANCE_POLL_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(worker.Redis, "from_url", lambda *a, **kw: SimpleNamespace(aclose=close_redis))
    monkeypatch.setattr(worker, "Bot", lambda _: SimpleNamespace(session=SimpleNamespace(close=close_bot)))
    monkeypatch.setattr(worker, "SessionFactory", FakeSession)
    monkeypatch.setattr(worker, "_heartbeat", heartbeat)
    monkeypatch.setattr(worker.NeironychBalanceAlertService, "poll_once", poll)
    monkeypatch.setattr(worker.NotificationDeliveryService, "claim_batch", claim)
    monkeypatch.setattr(worker, "_process_delivery", deliver)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(_DeliveryProcessed):
            await asyncio.wait_for(worker.run(), timeout=0.3)
    assert processed == [delivery_id]
    assert closed == ["redis", "bot"]
    assert len(poll_request_ids) == 1
    assert poll_request_ids[0] and poll_request_ids[0].startswith("neironych-balance:")
    assert request_id_var.get() is None
    category = (
        "deadline" if failure == "hung"
        else "auth" if failure in {401, 403}
        else "endpoint_missing" if failure == 404
        else "rate_limited" if failure == 429
        else "upstream_error" if failure == 503
        else "transport"
    )
    assert f"category={category}" in caplog.text
    assert "must-not-be-logged" not in caplog.text
    failure_records = [record for record in caplog.records if "neironych_balance_poll_failed" in record.message]
    assert len(failure_records) == 1
    assert isinstance(failure_records[0].duration_ms, float)
