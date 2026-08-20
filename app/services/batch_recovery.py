from __future__ import annotations

import uuid
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.batch_models import BatchGenerationCommand
from app.services.abuse_protection import AbuseProtectionService, GenerationAdmissionService
from app.services.billing_policy import BillingPolicyService
from app.services.batch_generation_core import (
    ACTIVE_STATUSES,
    BatchGenerationError,
    BatchIdempotencyConflict,
    amount,
    enqueue_generation,
    prepare_items,
    request_hash,
    wake_generations,
)
from app.services.batch_repository import BatchRepository
from app.services.credits import InternalCreditService


class BatchRecoveryService:
    @staticmethod
    async def quote(session: AsyncSession, *, user_id: uuid.UUID, batch_id: uuid.UUID) -> dict[str, object]:
        job = await BatchRepository.load(session, user_id=user_id, batch_id=batch_id)
        rows = await BatchRepository.rows(session, batch_id)
        if any(generation.status in ACTIVE_STATUSES for _item, generation in rows):
            raise BatchGenerationError("Batch is still running")
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
        existing, key, fingerprint = await cls.replay_check(
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

        rows = await BatchRepository.rows(session, batch_id)
        if any(generation.status in ACTIVE_STATUSES for _item, generation in rows):
            raise BatchGenerationError("Batch is still running")
        selected = [
            (item, generation)
            for item, generation in rows
            if generation.status == "failed"
        ]
        if not selected:
            session.add(
                BatchGenerationCommand(
                    batch_id=batch_id,
                    user_id=user_id,
                    kind="retry_failed",
                    idempotency_key=key,
                    request_hash=fingerprint,
                    result_generation_ids=[],
                )
            )
            await session.commit()
            return job, False, 0

        prepared = await prepare_items(
            session,
            model_id=job.model_id,
            prompt=job.prompt,
            parameters=job.parameters,
            billing_seconds=job.billing_seconds,
            input_urls=[item.input_url for item, _generation in selected],
        )
        total = sum((item.cost for item in prepared), Decimal("0"))
        admin_free = await BillingPolicyService.user_has_free_bot_access(session, user_id)
        charged_total = Decimal("0.00") if admin_free else total
        await AbuseProtectionService.generation_rate(redis, user_id)
        await GenerationAdmissionService.enforce(
            session,
            user_id=user_id,
            next_cost=charged_total,
        )
        generation_ids: list[uuid.UUID] = []
        for (batch_item, previous), prepared_item in zip(selected, prepared, strict=True):
            retry_count = batch_item.retry_count + 1
            generation = await enqueue_generation(
                session,
                user_id=user_id,
                batch_id=batch_id,
                item_id=batch_item.id,
                ordinal=batch_item.ordinal,
                prepared=prepared_item,
                prompt=job.prompt,
                parent_generation_id=previous.id,
                retry_count=retry_count,
                free_generation=admin_free,
            )
            batch_item.generation_id = generation.id
            batch_item.retry_count = retry_count
            generation_ids.append(generation.id)

        job.status = "running"
        job.completed_at = None
        job.total_charged_rox = Decimal(job.total_charged_rox) + charged_total
        session.add(
            BatchGenerationCommand(
                batch_id=batch_id,
                user_id=user_id,
                kind="retry_failed",
                idempotency_key=key,
                request_hash=fingerprint,
                result_generation_ids=[str(generation_id) for generation_id in generation_ids],
            )
        )
        await session.commit()
        await wake_generations(redis, generation_ids)
        return job, False, len(generation_ids)
