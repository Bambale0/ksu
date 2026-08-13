from __future__ import annotations

import uuid
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.batch_models import BatchGenerationCommand
from app.services.batch_generation_core import (
    BatchGenerationError,
    BatchIdempotencyConflict,
    amount,
    prepare_items,
    request_hash,
)
from app.services.batch_repository import BatchRepository
from app.services.credits import InternalCreditService


class BatchRecoveryService:
    @staticmethod
    async def quote(session: AsyncSession, *, user_id: uuid.UUID, batch_id: uuid.UUID) -> dict[str, object]:
        job = await BatchRepository.load(session, user_id=user_id, batch_id=batch_id)
        rows = await BatchRepository.rows(session, batch_id)
        urls = [item.input_url for item, generation in rows if generation.status == "failed"]
        if not urls:
            return {"failed_count": 0, "total_cost_credits": "0.00", "total_cost_rub": "0.00"}
        prepared = await prepare_items(
            session,
            model_id=job.model_id,
            prompt=job.prompt,
            parameters=job.parameters,
            billing_seconds=job.billing_seconds,
            input_urls=urls,
        )
        total = sum((item.cost for item in prepared), Decimal("0"))
        return {
            "failed_count": len(prepared),
            "total_cost_credits": amount(total),
            "total_cost_rub": amount(InternalCreditService.rubles_for(total)),
        }

    @staticmethod
    async def replay_check(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        batch_id: uuid.UUID,
        idempotency_key: str,
    ) -> tuple[BatchGenerationCommand | None, str, str]:
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise BatchGenerationError("Idempotency-Key must contain 1..128 characters")
        fingerprint = request_hash({"batch_id": str(batch_id), "kind": "retry_failed"})
        existing = await session.scalar(
            select(BatchGenerationCommand).where(
                BatchGenerationCommand.user_id == user_id,
                BatchGenerationCommand.idempotency_key == key,
            )
        )
        if existing is not None and (
            existing.batch_id != batch_id or existing.request_hash != fingerprint
        ):
            raise BatchIdempotencyConflict("Idempotency key was already used")
        return existing, key, fingerprint

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        batch_id: uuid.UUID,
        idempotency_key: str,
    ) -> tuple[object, bool, int]:
        _ = redis
        existing, _key, _fingerprint = await cls.replay_check(
            session,
            user_id=user_id,
            batch_id=batch_id,
            idempotency_key=idempotency_key,
        )
        job = await BatchRepository.load(
            session,
            user_id=user_id,
            batch_id=batch_id,
            lock=existing is None,
        )
        if existing is not None:
            return job, True, len(existing.result_generation_ids)
        return job, False, 0
