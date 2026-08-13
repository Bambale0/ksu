from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.batch_models import BatchGenerationJob


class BatchRepository:
    @staticmethod
    async def load(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        batch_id: uuid.UUID,
    ) -> BatchGenerationJob:
        job = await session.get(BatchGenerationJob, batch_id)
        if job is None or job.user_id != user_id:
            raise LookupError("Batch not found")
        return job
