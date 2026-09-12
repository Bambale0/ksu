from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

import app.api.webhooks as webhooks
from app.core.config import settings
from app.providers.kie import kie_generation_binding


class _FakeSession:
    def __init__(self, bound_generation_id: uuid.UUID | None) -> None:
        self.bound_generation_id = bound_generation_id

    async def scalar(self, _query):
        return self.bound_generation_id


class _FakeSessionFactory:
    def __init__(self, bound_generation_id: uuid.UUID | None) -> None:
        self.bound_generation_id = bound_generation_id

    def __call__(self):
        session = _FakeSession(self.bound_generation_id)

        class _Context:
            async def __aenter__(self):
                return session

            async def __aexit__(self, exc_type, exc, tb):
                return False

        return _Context()


@pytest.mark.asyncio
async def test_kie_webhook_accepts_bound_task_with_valid_scoped_binding_when_provider_hmac_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = uuid.uuid4()
    task_id = "task_prod_callback"
    key = "local-kie-webhook-key"
    binding = kie_generation_binding(generation_id, key)

    monkeypatch.setattr(settings, "kie_webhook_hmac_key", key)
    monkeypatch.setattr(webhooks, "SessionFactory", _FakeSessionFactory(generation_id))
    sync = AsyncMock(return_value=None)
    monkeypatch.setattr(webhooks.GenerationProviderService, "sync_kie_task", sync)

    app = FastAPI()
    app.include_router(webhooks.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/webhooks/kie?generation_id={generation_id}&binding={binding}",
            json={"code": 200, "data": {"taskId": task_id, "state": "success"}},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    sync.assert_awaited_once()
    assert sync.await_args.kwargs["task_id"] == task_id
    assert sync.await_args.kwargs["generation_id"] == generation_id


@pytest.mark.asyncio
async def test_kie_webhook_rejects_unsigned_callback_when_task_is_not_bound_to_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = uuid.uuid4()
    task_id = "attacker_task"
    key = "local-kie-webhook-key"
    binding = kie_generation_binding(generation_id, key)

    monkeypatch.setattr(settings, "kie_webhook_hmac_key", key)
    monkeypatch.setattr(webhooks, "SessionFactory", _FakeSessionFactory(None))
    sync = AsyncMock(return_value=None)
    monkeypatch.setattr(webhooks.GenerationProviderService, "sync_kie_task", sync)

    app = FastAPI()
    app.include_router(webhooks.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/webhooks/kie?generation_id={generation_id}&binding={binding}",
            json={"code": 200, "data": {"taskId": task_id, "state": "success"}},
        )

    assert response.status_code == 403
    sync.assert_not_awaited()
