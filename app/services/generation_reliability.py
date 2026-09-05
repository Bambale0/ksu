from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation
from app.db.reliability_models import GenerationOutbox

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ClaimedGeneration:
    outbox_id: uuid.UUID
    generation_id: uuid.UUID
    attempts: int


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def retry_delay_seconds(attempt: int) -> int:
    """Small exponential backoff, capped to keep recovery responsive."""

    return min(300, 2 ** max(1, min(attempt, 8)))


class GenerationOutboxService:
    @staticmethod
    def add(session: AsyncSession, generation_id: uuid.UUID) -> GenerationOutbox:
        row = GenerationOutbox(generation_id=generation_id)
        session.add(row)
        return row

    @staticmethod
    async def ensure_missing(session: AsyncSession, *, limit: int = 100) -> int:
        """Repair legacy/manual queued generations that do not have an outbox row."""

        ids = list(
            (
                await session.scalars(
                    select(Generation.id)
                    .outerjoin(
                        GenerationOutbox,
                        GenerationOutbox.generation_id == Generation.id,
                    )
                    .where(
                        Generation.status.in_(("queued", "retry")),
                        GenerationOutbox.id.is_(None),
                    )
                    .order_by(Generation.created_at.asc())
                    .limit(limit)
                )
            ).all()
        )
        if not ids:
            return 0

        for generation_id in ids:
            statement = (
                pg_insert(GenerationOutbox)
                .values(
                    id=uuid.uuid4(),
                    generation_id=generation_id,
                    status="pending",
                    attempts=0,
                    available_at=utcnow(),
                )
                .on_conflict_do_nothing(index_elements=[GenerationOutbox.generation_id])
            )
            await session.execute(statement)
        await session.commit()
        return len(ids)

    @staticmethod
    async def claim(session: AsyncSession) -> ClaimedGeneration | None:
        now = utcnow()
        row = await session.scalar(
            select(GenerationOutbox)
            .where(
                GenerationOutbox.available_at <= now,
                or_(
                    GenerationOutbox.status == "pending",
                    and_(
                        GenerationOutbox.status == "processing",
                        GenerationOutbox.lease_until.is_not(None),
                        GenerationOutbox.lease_until < now,
                    ),
                ),
            )
            .order_by(GenerationOutbox.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return None

        row.status = "processing"
        row.attempts += 1
        row.lease_until = now + timedelta(seconds=settings.generation_outbox_lease_seconds)
        row.last_error = None
        await session.commit()
        return ClaimedGeneration(
            outbox_id=row.id,
            generation_id=row.generation_id,
            attempts=row.attempts,
        )

    @staticmethod
    async def complete(session: AsyncSession, outbox_id: uuid.UUID) -> None:
        row = await session.scalar(
            select(GenerationOutbox)
            .where(GenerationOutbox.id == outbox_id)
            .with_for_update()
        )
        if row is None:
            return
        row.status = "completed"
        row.lease_until = None
        row.completed_at = utcnow()
        row.last_error = None
        await session.commit()

    @staticmethod
    async def fail(session: AsyncSession, outbox_id: uuid.UUID, error: str) -> None:
        row = await session.scalar(
            select(GenerationOutbox)
            .where(GenerationOutbox.id == outbox_id)
            .with_for_update()
        )
        if row is None:
            return
        row.status = "failed"
        row.lease_until = None
        row.completed_at = utcnow()
        row.last_error = error[:4000]
        await session.commit()

    @staticmethod
    async def release(
        session: AsyncSession,
        outbox_id: uuid.UUID,
        *,
        error: str = "",
        delay_seconds: int | None = None,
    ) -> None:
        row = await session.scalar(
            select(GenerationOutbox)
            .where(GenerationOutbox.id == outbox_id)
            .with_for_update()
        )
        if row is None:
            return
        delay = retry_delay_seconds(row.attempts) if delay_seconds is None else max(delay_seconds, 1)
        row.status = "pending"
        row.lease_until = None
        row.available_at = utcnow() + timedelta(seconds=delay)
        row.last_error = error[:4000] or None
        await session.commit()

    @staticmethod
    async def requeue_generation(
        session: AsyncSession,
        generation_id: uuid.UUID,
        *,
        reason: str = "",
    ) -> None:
        """Open a fresh durable stage for an already-submitted generation.

        Pinterest Repeat uses this after a provider callback has produced a candidate
        that still needs AI quality evaluation. Resetting attempts is intentional:
        the provider submission stage already completed successfully and quality
        evaluation/corrective submission is a new bounded stage.
        """

        row = await session.scalar(
            select(GenerationOutbox)
            .where(GenerationOutbox.generation_id == generation_id)
            .with_for_update()
        )
        if row is None:
            row = GenerationOutbox(generation_id=generation_id)
            session.add(row)
        row.status = "pending"
        row.attempts = 0
        row.available_at = utcnow()
        row.lease_until = None
        row.completed_at = None
        row.last_error = reason[:4000] or None
        await session.commit()

    @staticmethod
    async def mark_generation_terminal(
        session: AsyncSession,
        generation_id: uuid.UUID,
        *,
        failed: bool,
        error: str = "",
    ) -> None:
        row = await session.scalar(
            select(GenerationOutbox)
            .where(GenerationOutbox.generation_id == generation_id)
            .with_for_update()
        )
        if row is None:
            return
        row.status = "failed" if failed else "completed"
        row.lease_until = None
        row.completed_at = utcnow()
        row.last_error = error[:4000] or None
        await session.commit()
