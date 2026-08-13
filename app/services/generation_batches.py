from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.batch_generation_core import amount, prepare_items, resolve_inputs
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
