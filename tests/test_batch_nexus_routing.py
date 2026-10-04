from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.services.batch_generation_core import PreparedBatchItem, enqueue_generation
from app.services.model_catalog import ModelCatalog


@pytest.mark.asyncio
async def test_batch_generation_uses_same_nexus_route_snapshot_as_regular_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.added = []

        def add(self, value) -> None:
            self.added.append(value)

        async def flush(self) -> None:
            return None

        async def get(self, *_args, **_kwargs):
            return None

    session = FakeSession()
    outbox_ids: list[uuid.UUID] = []
    debit = AsyncMock()

    monkeypatch.setattr(
        "app.services.batch_generation_core.GenerationOutboxService.add",
        lambda _session, generation_id: outbox_ids.append(generation_id),
    )
    monkeypatch.setattr(
        "app.services.batch_generation_core.WalletService.debit",
        debit,
    )

    spec = ModelCatalog.get("gpt-image-2-i2i")
    prepared = PreparedBatchItem(
        input_url="https://cdn.example.test/source.png",
        spec=spec,
        clean={
            "prompt": "edit",
            "input_urls": ["https://cdn.example.test/source.png"],
            "aspect_ratio": "1:1",
        },
        cost=Decimal("1.00"),
        billing_seconds=None,
        unit_price=Decimal("1.00"),
    )

    generation = await enqueue_generation(
        session,  # type: ignore[arg-type]
        user_id=uuid.uuid4(),
        batch_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        ordinal=1,
        prepared=prepared,
        prompt="edit",
    )

    assert generation.provider == "nexus"
    assert generation.parameters["_provider_route"] == ["nexus", "kie"]
    assert generation.parameters["_provider_route_index"] == 0
    assert generation.parameters["_provider_route_revision"] == 1
    debit.assert_awaited_once()
    assert outbox_ids == [generation.id]
