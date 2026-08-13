from __future__ import annotations

import random
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.batch_models import BatchGenerationJob
from app.db.models import Generation, User, Wallet
from app.db.reliability_models import GenerationOutbox
from app.db.session import SessionFactory
from app.services.batch_generation_core import BatchIdempotencyConflict
from app.services.batch_repository import BatchRepository
from app.services.generation_batches import GenerationBatchService
from app.services.wallet import InsufficientBalanceError, WalletService


async def _user(session, balance: Decimal = Decimal("100")) -> User:  # type: ignore[no-untyped-def]
    user = User(
        telegram_id=random.randint(8_000_000_000_000, 8_999_999_999_999),
        first_name="Batch user",
    )
    session.add(user)
    await session.flush()
    await WalletService.credit(
        session,
        user_id=user.id,
        amount=balance,
        kind="test_seed",
        reference_type="test",
        reference_id=str(user.id),
        idempotency_key=f"batch-seed:{user.id}",
    )
    await session.commit()
    return user


@pytest.mark.asyncio
async def test_batch_create_is_atomic_and_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    async with SessionFactory() as session:
        user = await _user(session)
        key = f"batch-{uuid.uuid4()}"
        payload = {
            "user_id": user.id,
            "model_id": "nano-banana-edit",
            "prompt": "Keep the subject, change the background",
            "parameters": {"aspect_ratio": "1:1", "output_format": "png"},
            "billing_seconds": None,
            "input_urls": [
                "https://cdn.example.invalid/a.png",
                "https://cdn.example.invalid/b.png",
            ],
            "reference_ids": [],
            "idempotency_key": key,
        }
        first, replayed_first = await GenerationBatchService.create(
            session, AsyncMock(), **payload
        )
        first_id = first.id
        first_cost = Decimal(first.initial_cost_rox)
        second, replayed_second = await GenerationBatchService.create(
            session, AsyncMock(), **payload
        )
        wallet = await session.get(Wallet, user.id)
        generation_count = int(
            await session.scalar(
                select(func.count()).select_from(Generation).where(Generation.user_id == user.id)
            )
            or 0
        )
        outbox_count = int(await session.scalar(select(func.count()).select_from(GenerationOutbox)) or 0)
        assert replayed_first is False
        assert replayed_second is True
        assert second.id == first_id
        assert generation_count == 2
        assert outbox_count >= 2
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("100") - first_cost

        conflicting = {**payload, "prompt": "Different request"}
        with pytest.raises(BatchIdempotencyConflict):
            await GenerationBatchService.create(session, AsyncMock(), **conflicting)


@pytest.mark.asyncio
async def test_batch_insufficient_balance_rolls_back_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    async with SessionFactory() as session:
        user = await _user(session, Decimal("1"))
        user_id = user.id
        with pytest.raises(InsufficientBalanceError):
            await GenerationBatchService.create(
                session,
                AsyncMock(),
                user_id=user_id,
                model_id="nano-banana-edit",
                prompt="Edit both",
                parameters={"aspect_ratio": "1:1", "output_format": "png"},
                billing_seconds=None,
                input_urls=[
                    "https://cdn.example.invalid/c.png",
                    "https://cdn.example.invalid/d.png",
                ],
                reference_ids=[],
                idempotency_key=f"batch-poor-{uuid.uuid4()}",
            )
        await session.rollback()
        batch_count = int(
            await session.scalar(
                select(func.count())
                .select_from(BatchGenerationJob)
                .where(BatchGenerationJob.user_id == user_id)
            )
            or 0
        )
        generation_count = int(
            await session.scalar(
                select(func.count()).select_from(Generation).where(Generation.user_id == user_id)
            )
            or 0
        )
        assert batch_count == 0
        assert generation_count == 0
        wallet = await session.get(Wallet, user_id)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("1")


@pytest.mark.asyncio
async def test_batch_progress_becomes_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    async with SessionFactory() as session:
        user = await _user(session)
        job, _ = await GenerationBatchService.create(
            session,
            AsyncMock(),
            user_id=user.id,
            model_id="nano-banana-edit",
            prompt="Edit both",
            parameters={"aspect_ratio": "1:1", "output_format": "png"},
            billing_seconds=None,
            input_urls=[
                "https://cdn.example.invalid/e.png",
                "https://cdn.example.invalid/f.png",
            ],
            reference_ids=[],
            idempotency_key=f"batch-progress-{uuid.uuid4()}",
        )
        rows = await BatchRepository.rows(session, job.id)
        rows[0][1].status = "succeeded"
        rows[1][1].status = "failed"
        await session.commit()
        status_value, succeeded, failed, active = await BatchRepository.refresh(session, job)
        assert status_value == "partial"
        assert (succeeded, failed, active) == (1, 1, 0)
