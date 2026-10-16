from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.db.models import Generation
from app.providers.nexus import NexusClient
from app.workers.notifications import _send_generation_notification


@pytest.mark.asyncio
async def test_nexus_prompt_limit_is_explained_in_customer_notification(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_prompt = "private customer prompt " * 200

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{
            "type": "string_too_long",
            "loc": ["body", "params", "seedream-5.0-pro", "prompt"],
            "msg": "String should have at most 4000 characters",
            "input": private_prompt,
            "ctx": {"max_length": 4000},
        }]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://nexus.example",
    ) as http_client:
        client = NexusClient("synthetic-key", client=http_client)
        with pytest.raises(httpx.HTTPStatusError) as rejected:
            await client.create_generation(
                params={"model_name": "seedream-5.0-pro", "prompt": private_prompt},
                idempotency_key="generation:prompt-limit",
            )

    generation = Generation(
        id=uuid.uuid4(), user_id=uuid.uuid4(), kind="image", provider="nexus",
        status="failed", prompt=private_prompt, cost_rox=Decimal("20"),
        parameters={"_model_id": "seedream-5-pro-i2i"}, error=str(rejected.value),
    )
    messages: list[str] = []

    class RecordingBot:
        async def send_message(self, *, text: str, **_kwargs: Any) -> None:
            messages.append(text)

    await _send_generation_notification(
        RecordingBot(), session=None, chat_id=123,
        notification=SimpleNamespace(kind="generation_failed"), generation=generation,
    )

    assert len(messages) == 1
    assert (
        "Промпт слишком длинный. Максимум — 4000 символов. "
        "Сократите текст и повторите генерацию."
    ) in messages[0]
    assert "20 ROX возвращены на баланс" in messages[0]
    assert str(generation.id) in messages[0]
    assert "private customer prompt" not in messages[0]
    assert "nexus.example" not in messages[0]
    assert "private customer prompt" not in caplog.text
