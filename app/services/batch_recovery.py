from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.batch_generation_core import amount, prepare_items
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
