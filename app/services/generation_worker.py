from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.config import settings
from app.db.models import Generation
from app.db.session import SessionFactory
from app.services.generation_provider import GenerationProviderService
from app.services.generation_reliability import GenerationOutboxService, utcnow

logger = logging.getLogger(__name__)


class GenerationWorkerService:
    @classmethod
    async def process_one(cls) -> bool:
        async with SessionFactory() as session:
            claim = await GenerationOutboxService.claim(session)
        if claim is None:
            return False

        async with SessionFactory() as session:
            generation = await session.get(Generation, claim.generation_id)
            if generation is None:
                await GenerationOutboxService.fail(
                    session,
                    claim.outbox_id,
                    "Generation row no longer exists",
                )
                return True

            if generation.status == "succeeded":
                await GenerationOutboxService.complete(session, claim.outbox_id)
                return True
            if generation.status == "failed":
                await GenerationOutboxService.fail(
                    session,
                    claim.outbox_id,
                    generation.error or "Generation failed",
                )
                return True
            if generation.external_id and generation.status in {"generating", "submitting"}:
                # Provider submission is already durable locally. Callback/poller owns completion.
                await GenerationOutboxService.complete(session, claim.outbox_id)
                return True

            if generation.status == "submitting" and generation.external_id is None:
                # Never blindly repeat an uncertain createTask call: it could duplicate provider spend.
                age = utcnow() - generation.updated_at
                if age.total_seconds() >= settings.generation_submission_unknown_timeout_seconds:
                    message = "Kie submission outcome remained unknown after worker interruption"
                    await GenerationProviderService.fail_and_refund(session, generation.id, message)
                    await GenerationOutboxService.fail(session, claim.outbox_id, message)
                else:
                    await GenerationOutboxService.release(
                        session,
                        claim.outbox_id,
                        error="Waiting for callback to recover uncertain Kie submission",
                        delay_seconds=min(30, settings.generation_worker_poll_seconds * 3),
                    )
                return True

            if generation.status not in {"queued", "retry"}:
                await GenerationOutboxService.complete(session, claim.outbox_id)
                return True

            try:
                result = await GenerationProviderService.submit_kie(session, generation.id)
            except Exception as exc:
                # submit_kie refunds and makes the generation terminal on provider failure.
                logger.exception("Generation submission failed: %s", generation.id)
                refreshed = await session.get(Generation, generation.id)
                if refreshed is not None and refreshed.status == "failed":
                    await GenerationOutboxService.fail(session, claim.outbox_id, str(exc))
                elif claim.attempts >= settings.generation_submission_max_attempts:
                    message = f"Generation submission retries exhausted: {exc}"
                    await GenerationProviderService.fail_and_refund(session, generation.id, message)
                    await GenerationOutboxService.fail(session, claim.outbox_id, message)
                else:
                    await GenerationOutboxService.release(
                        session,
                        claim.outbox_id,
                        error=str(exc),
                    )
                return True

            if result.status == "failed":
                await GenerationOutboxService.fail(
                    session,
                    claim.outbox_id,
                    result.error or "Generation failed",
                )
            elif result.external_id or result.status in {"generating", "succeeded"}:
                await GenerationOutboxService.complete(session, claim.outbox_id)
            else:
                await GenerationOutboxService.release(
                    session,
                    claim.outbox_id,
                    error=f"Unexpected post-submit state: {result.status}",
                )
            return True

    @classmethod
    async def recovery_once(cls) -> None:
        """Repair queue gaps and poll stale Kie tasks as callback fallback."""

        async with SessionFactory() as session:
            repaired = await GenerationOutboxService.ensure_missing(
                session,
                limit=settings.generation_recovery_batch_size,
            )
            if repaired:
                logger.warning("Recovered %s queued generations without outbox rows", repaired)

        await cls._expire_unknown_submissions()
        await cls._reconcile_stale_generating()

    @classmethod
    async def _expire_unknown_submissions(cls) -> None:
        cutoff = utcnow() - timedelta(seconds=settings.generation_submission_unknown_timeout_seconds)
        async with SessionFactory() as session:
            ids = list(
                (
                    await session.scalars(
                        select(Generation.id)
                        .where(
                            Generation.status == "submitting",
                            Generation.external_id.is_(None),
                            Generation.updated_at < cutoff,
                        )
                        .order_by(Generation.updated_at.asc())
                        .limit(settings.generation_recovery_batch_size)
                    )
                ).all()
            )

        for generation_id in ids:
            async with SessionFactory() as session:
                generation = await session.get(Generation, generation_id)
                if (
                    generation is None
                    or generation.status != "submitting"
                    or generation.external_id is not None
                    or generation.updated_at >= cutoff
                ):
                    continue
                message = "Kie submission outcome timed out before task id was persisted"
                await GenerationProviderService.fail_and_refund(session, generation.id, message)

    @classmethod
    async def _reconcile_stale_generating(cls) -> None:
        cutoff = utcnow() - timedelta(seconds=settings.generation_reconcile_stale_seconds)
        async with SessionFactory() as session:
            tasks = list(
                (
                    await session.execute(
                        select(Generation.id, Generation.external_id)
                        .where(
                            Generation.status == "generating",
                            Generation.external_id.is_not(None),
                            Generation.updated_at < cutoff,
                        )
                        .order_by(Generation.updated_at.asc())
                        .limit(settings.generation_recovery_batch_size)
                    )
                ).all()
            )

        for generation_id, external_id in tasks:
            if not external_id:
                continue
            async with SessionFactory() as session:
                try:
                    await GenerationProviderService.sync_kie_task(
                        session,
                        task_id=str(external_id),
                        generation_id=generation_id,
                    )
                except Exception:
                    # Reconciliation is a fallback. Do not fail/refund a task merely because
                    # the status endpoint is temporarily unavailable.
                    logger.exception("Kie reconciliation failed for %s", generation_id)
