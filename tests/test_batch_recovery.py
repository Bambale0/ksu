from __future__ import annotations

import random
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.db.models import Generation, User, Wallet
from app.db.session import SessionFactory
from app.services.batch_recovery import BatchRecoveryService
from app.services.batch_repository import BatchRepository
from app.services.generation_batches import GenerationBatchService
from app.services.wallet import WalletService


async def _funded_user(session) -> User:  # type: ignore[no-untyped-def]
    user = User(
        telegram_id=random.randint(7_000_000_000_000, 7_999_999_999_999),
        first_name="Batch recovery user",
    )
    session.add(user)
    await session.flush()
    await WalletService.credit(
        session,
        user_id=user.id,
        amount=Decimal("1000"),
        kind="test_seed",
        reference_type="test",
        reference_id=str(user.id),
        idempotency_key=f"batch-recovery-seed:{user.id}",
    )
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_failed_item_recovery_charges_once_and_keeps_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    async with SessionFactory() as session:
        user = await _funded_user(session)
        job, _ = await GenerationBatchService.create(
            session,
            AsyncMock(),
            user_id=user.id,
            model_id="gpt-image-2-i2i",
            prompt="Edit both",
            parameters={"aspect_ratio": "1:1"},
            billing_seconds=None,
            input_urls=[
                "https://cdn.example.invalid/recovery-a.png",
                "https://cdn.example.invalid/recovery-b.png",
            ],
            reference_ids=[],
            idempotency_key=f"batch-recovery-{uuid.uuid4()}",
        )
        rows = await BatchRepository.rows(session, job.id)
        failed_item, failed_generation = rows[0]
        failed_generation.status = "failed"
        rows[1][1].status = "succeeded"
        await session.commit()
        failed_generation_id = failed_generation.id

        quote = await BatchRecoveryService.quote(
            session,
            user_id=user.id,
            batch_id=job.id,
        )
        retry_cost = Decimal(str(quote["total_cost_credits"]))
        wallet_before = await session.get(Wallet, user.id)
        assert wallet_before is not None
        balance_before = Decimal(wallet_before.balance)

        key = f"batch-retry-{uuid.uuid4()}"
        _job, replayed_first, retried_first = await BatchRecoveryService.execute(
            session,
            AsyncMock(),
            user_id=user.id,
            batch_id=job.id,
            idempotency_key=key,
        )
        _job, replayed_second, retried_second = await BatchRecoveryService.execute(
            session,
            AsyncMock(),
            user_id=user.id,
            batch_id=job.id,
            idempotency_key=key,
        )
        refreshed_item = await session.get(type(failed_item), failed_item.id)
        assert refreshed_item is not None
        new_generation = await session.get(Generation, refreshed_item.generation_id)
        wallet_after = await session.get(Wallet, user.id)
        assert replayed_first is False
        assert replayed_second is True
        assert retried_first == 1
        assert retried_second == 1
        assert refreshed_item.retry_count == 1
        assert new_generation is not None
        assert new_generation.id != failed_generation_id
        assert new_generation.parent_generation_id == failed_generation_id
        assert new_generation.action_type == "batch_retry"
        assert wallet_after is not None
        assert Decimal(wallet_after.balance) == balance_before - retry_cost
