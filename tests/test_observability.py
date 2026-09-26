import json
import logging
import uuid
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from prometheus_client import generate_latest
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import JsonFormatter, ObservabilityFilter
from app.core.observability import (
    DISTRIBUTED_EVENT_NAMES,
    DISTRIBUTED_EVENTS,
    heartbeat_key,
    record_distributed_event,
    record_worker_heartbeat,
    worker_health,
)
from app.main import app


@pytest.mark.asyncio
async def test_request_id_is_preserved_on_response() -> None:
    request_id = f"test-{uuid.uuid4()}"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.asyncio
async def test_invalid_request_id_is_replaced() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live", headers={"X-Request-ID": "bad id with spaces"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "bad id with spaces"
    assert response.headers["X-Request-ID"]


def test_json_log_contains_correlation_fields() -> None:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    ObservabilityFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "hello world"
    assert "request_id" in payload
    assert "trace_id" in payload
    assert "span_id" in payload


def test_media_worker_music_events_are_registered() -> None:
    assert "music_audio_ingest_processed" in DISTRIBUTED_EVENT_NAMES
    assert "music_audio_worker_loop_error" in DISTRIBUTED_EVENT_NAMES


@pytest.mark.asyncio
async def test_worker_heartbeat_and_distributed_event_use_real_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    worker = f"test-worker-{uuid.uuid4()}"
    event = "generation_submit_success"
    event_key = f"observability:event:{event}"
    monkeypatch.setattr(settings, "worker_stale_after_seconds", 120)
    try:
        await redis.delete(heartbeat_key(worker), event_key)
        missing = await worker_health(redis, worker)
        assert missing["up"] is False

        await record_worker_heartbeat(redis, worker)
        healthy = await worker_health(redis, worker)
        assert healthy["up"] is True
        assert healthy["age_seconds"] is not None

        before = int(await redis.get(event_key) or 0)
        await record_distributed_event(redis, event)
        after = int(await redis.get(event_key) or 0)
        assert after == before + 1
        DISTRIBUTED_EVENTS.labels(event=event).set(after)
        metrics = generate_latest().decode("utf-8")
        assert 'ksu_distributed_event_count{event="generation_submit_success"}' in metrics
    finally:
        await redis.delete(heartbeat_key(worker), event_key)
        await redis.aclose()


@pytest.mark.asyncio
async def test_operational_health_fails_when_card_webhook_secret_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import health

    async def healthy_worker(_redis: object, worker: str) -> dict[str, object]:
        return {"worker": worker, "up": True, "age_seconds": 0}

    monkeypatch.setattr(health, "worker_health", healthy_worker)
    monkeypatch.setattr(settings, "card_api_key", "enabled")
    monkeypatch.setattr(settings, "card_webhook_key", "")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=object())))

    with pytest.raises(HTTPException) as exc_info:
        await health.operational(request)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["status"] == "degraded"
    assert exc_info.value.detail["configuration"] == [
        {"component": "card-payments", "reason": "card_webhook_key_missing"}
    ]


@pytest.mark.asyncio
async def test_operational_health_allows_disabled_card_checkout_without_webhook_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import health

    async def healthy_worker(_redis: object, worker: str) -> dict[str, object]:
        return {"worker": worker, "up": True, "age_seconds": 0}

    monkeypatch.setattr(health, "worker_health", healthy_worker)
    monkeypatch.setattr(settings, "card_api_key", "")
    monkeypatch.setattr(settings, "card_webhook_key", "")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=object())))

    result = await health.operational(request)  # type: ignore[arg-type]

    assert result["status"] == "operational"
    assert "configuration" not in result
