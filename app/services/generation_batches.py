from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.batch_models import BatchGenerationItem, BatchGenerationJob
from app.services.abuse_protection import AbuseProtectionService, GenerationAdmissionService
from app.services.batch_generation_core import (
    BatchGenerationError,
    BatchIdempotencyConflict,
    amount,
    enqueue_generation,
    prepare_items,
    request_hash,
    resolve_inputs,
    wake_generations,
)
from app.services.credits import InternalCreditService


class GenerationBatchService:
    MIN_ITEMS = 2
    MAX_ITEMS = 20

    @classmethod
    async def resolve(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        input_urls: list[str],
        reference_ids: list[uuid.UUID],
    ) -> list[str]:
        return await resolve_inputs(
            session,
            user_id=user_id,
            input_urls=input_urls,
            reference_ids=reference_ids,
            min_items=cls.MIN_ITEMS,
            max_items=cls.MAX_ITEMS,
        )

    @classmethod
    async def quote(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        model_id: str,
        prompt: str,
        parameters: dict[str, Any],
        billing_seconds: int | None,
        input_urls: list[str],
        reference_ids: list[uuid.UUID],
    ) -> dict[str, Any]:
        resolved = await cls.resolve(
            session,
            user_id=user_id,
            input_urls=input_urls,
            reference_ids=reference_ids,
        )
        prepared = await prepare_items(
            session,
            model_id=model_id,
            prompt=prompt,
            parameters=parameters,
            billing_seconds=billing_seconds,
            input_urls=resolved,
        )
        total = sum((item.cost for item in prepared), Decimal("0"))
        costs = sorted({amount(item.cost) for item in prepared})
        spec = prepared[0].spec
        return {
            "model": {"id": spec.id, "title": spec.title, "family": spec.family},
            "input_count": len(prepared),
            "per_item_cost_credits": costs[0] if len(costs) == 1 else None,
            "total_cost_credits": amount(total),
            "total_cost_rub": amount(InternalCreditService.rubles_for(total)),
            "billing_seconds": prepared[0].billing_seconds,
        }

    @classmethod
    async def create(
        cls,
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        model_id: str,
        prompt: str,
        parameters: dict[str, Any],
        billing_seconds: int | None,
        input_urls: list[str],
        reference_ids: list[uuid.UUID],
        idempotency_key: str,
    ) -> tuple[BatchGenerationJob, bool]:
        key = idempotency_key.strip()
        if not key or len(key) > 128:
            raise BatchGenerationError("Idempotency-Key must contain 1..128 characters")
        resolved = await cls.resolve(
            session,
            user_id=user_id,
            input_urls=input_urls,
            reference_ids=reference_ids,
        )
        fingerprint = request_hash(
            {
                "model_id": model_id,
                "prompt": prompt,
                "parameters": parameters,
                "billing_seconds": billing_seconds,
                "input_urls": resolved,
            }
        )
        existing = await session.scalar(
            select(BatchGenerationJob).where(
                BatchGenerationJob.user_id == user_id,
                BatchGenerationJob.idempotency_key == key,
            )
        )
        if existing is not None:
            if existing.request_hash != fingerprint:
                raise BatchIdempotencyConflict(
                    "Idempotency key was already used for another batch"
                )
            return existing, True

        prepared = await prepare_items(
            session,
            model_id=model_id,
            prompt=prompt,
            parameters=parameters,
            billing_seconds=billing_seconds,
            input_urls=resolved,
        )
        total = sum((item.cost for item in prepared), Decimal("0"))
        await AbuseProtectionService.generation_rate(redis, user_id)
        await GenerationAdmissionService.enforce(
            session,
            user_id=user_id,
            next_cost=total,
        )

        job = BatchGenerationJob(
            user_id=user_id,
            status="running",
            model_id=model_id,
            prompt=prompt,
            parameters=dict(parameters),
            billing_seconds=billing_seconds,
            input_count=len(prepared),
            initial_cost_rox=total,
            total_charged_rox=total,
            idempotency_key=key,
            request_hash=fingerprint,
        )
        session.add(job)
        await session.flush()

        generation_ids: list[uuid.UUID] = []
        for ordinal, prepared_item in enumerate(prepared):
            item_id = uuid.uuid4()
            generation = await enqueue_generation(
                session,
                user_id=user_id,
                batch_id=job.id,
                item_id=item_id,
                ordinal=ordinal,
                prepared=prepared_item,
                prompt=prompt,
            )
            session.add(
                BatchGenerationItem(
                    id=item_id,
                    batch_id=job.id,
                    ordinal=ordinal,
                    input_url=prepared_item.input_url,
                    generation_id=generation.id,
                    retry_count=0,
                )
            )
            generation_ids.append(generation.id)

        await session.commit()
        await wake_generations(redis, generation_ids)
        return job, False
