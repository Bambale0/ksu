from __future__ import annotations

import uuid
from datetime import datetime, timezone

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

    @classmethod
    async def refresh(cls, session: AsyncSession, job: BatchGenerationJob) -> tuple[str, int, int, int]:
        rows = await cls.rows(session, job.id)
        succeeded = sum(g.status == "succeeded" for _item, g in rows)
        failed = sum(g.status == "failed" for _item, g in rows)
        active = sum(g.status in {"queued", "retry", "submitting", "generating"} for _item, g in rows)
        if succeeded == job.input_count:
            status = "succeeded"
        elif active:
            status = "running"
        elif succeeded and failed:
            status = "partial"
        else:
            status = "failed"
        job.status = status
        job.succeeded_count = succeeded
        job.failed_count = failed
        job.completed_at = None if status == "running" else datetime.now(timezone.utc)
        await session.commit()
        return status, succeeded, failed, active
