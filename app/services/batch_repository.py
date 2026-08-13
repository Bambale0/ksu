from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.batch_models import BatchGenerationItem, BatchGenerationJob
from app.db.models import Generation


class BatchRepository:
    @staticmethod
    async def load(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        batch_id: uuid.UUID,
        lock: bool = False,
    ) -> BatchGenerationJob:
        job = await session.get(BatchGenerationJob, batch_id, with_for_update=lock)
        if job is None or job.user_id != user_id:
            raise LookupError("Batch not found")
        return job

    @staticmethod
    async def rows(
        session: AsyncSession,
        batch_id: uuid.UUID,
    ) -> list[tuple[BatchGenerationItem, Generation]]:
        result = await session.execute(
            select(BatchGenerationItem, Generation)
            .join(Generation, Generation.id == BatchGenerationItem.generation_id)
            .where(BatchGenerationItem.batch_id == batch_id)
            .order_by(BatchGenerationItem.ordinal.asc())
        )
        return list(result.all())
