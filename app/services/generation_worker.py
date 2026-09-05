from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Generation
from app.db.session import SessionFactory
from app.services.abuse_protection import AbuseProtectionService, ResourcePolicyError
from app.services.generation_provider import GenerationProviderService
from app.services.generation_reliability import GenerationOutboxService, utcnow
from app.services.pinterest_quality_gate import PinterestRepeatQualityGate

logger = logging.getLogger(__name__)


class GenerationWorkerService:
    @classmethod
    async def process_one(cls, redis: Redis) -> bool:
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

            if PinterestRepeatQualityGate.is_pending(generation):
                try:
                    outcome = await PinterestRepeatQualityGate.process_pending(
                        session,
                        redis,
                        generation,
                    )
                except ResourcePolicyError as exc:
                    await GenerationOutboxService.release(
                        session,
                        claim.outbox_id,
                        error=str(exc),
                        delay_seconds=exc.retry_after,
                    )
                    return True
                if outcome == "retry_generation":
                    await GenerationOutboxService.release(
                        session,
                        claim.outbox_id,
                        error="Pinterest quality gate scheduled one corrective retry",
                        delay_seconds=1,
                    )
                return True

            if generation.external_id and generation.status in {"generating", "submitting"}:
                if generation.action_type == "pinterest_repeat":
                    await GenerationOutboxService.complete_submission_stage(
                        session,
                        claim.outbox_id,
                        generation.id,
                    )
                else:
                    await GenerationOutboxService.complete(session, claim.outbox_id)
                return True

            if generation.status == "submitting" and generation.external_id is None:
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
                await AbuseProtectionService.provider_submission_gate(redis, "kie")
            except ResourcePolicyError as exc:
                # Resource throttling is not a generation failure and must not refund.
                # Keep the durable outbox pending until the provider guard allows work.
                await GenerationOutboxService.release(
                    session,
                    claim.outbox_id,
                    error=str(exc),
                    delay_seconds=exc.retry_after,
                )
                return True

            try:
                result = await GenerationProviderService.submit_kie(session, generation.id)
            except Exception as exc:
                if AbuseProtectionService.availability_failure(exc):
                    await AbuseProtectionService.record_provider_failure(redis, "kie")
                logger.exception("Generation submission failed: %s", generation.id)
                refreshed = await session.get(Generation, generation.id)
                if refreshed is None:
                    await GenerationOutboxService.fail(
                        session,
                        claim.outbox_id,
                        "Generation disappeared after provider submission error",
                    )
                elif refreshed.status == "succeeded":
                    # A callback may have completed the generation while the worker
                    # observed an ambiguous provider response.
                    await GenerationOutboxService.complete(session, claim.outbox_id)
                elif refreshed.status == "failed":
                    await GenerationOutboxService.fail(session, claim.outbox_id, str(exc))
                elif refreshed.status == "submitting" and refreshed.external_id is None:
                    # Do not resubmit an ambiguous createTask outcome: the original
                    # request may already have created a billable provider task.
                    await GenerationOutboxService.release(
                        session,
                        claim.outbox_id,
                        error="Waiting for callback to recover uncertain Kie submission",
                        delay_seconds=min(30, settings.generation_worker_poll_seconds * 3),
                    )
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

            await AbuseProtectionService.record_provider_success(redis, "kie")
            if result.status == "failed":
                await GenerationOutboxService.fail(
                    session,
                    claim.outbox_id,
                    result.error or "Generation failed",
                )
            elif result.external_id or result.status in {"generating", "succeeded"}:
                if result.action_type == "pinterest_repeat":
                    await GenerationOutboxService.complete_submission_stage(
                        session,
                        claim.outbox_id,
                        result.id,
                    )
                else:
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
        """Repair queue gaps and reconcile stale/expired Kie tasks."""

        async with SessionFactory() as session:
            repaired = await GenerationOutboxService.ensure_missing(
                session,
                limit=settings.generation_recovery_batch_size,
            )
            if repaired:
                logger.warning("Recovered %s queued generations without outbox rows", repaired)

        await cls._expire_unknown_submissions()
        await cls._expire_stuck_generations()
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

    @staticmethod
    def _provider_started_at(generation: Generation) -> datetime:
        raw = (generation.parameters or {}).get("_provider_submitted_at")
        if isinstance(raw, str) and raw.strip():
            try:
                value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                return value.astimezone(timezone.utc)
            except ValueError:
                logger.warning(
                    "Generation %s has invalid _provider_submitted_at=%r",
                    generation.id,
                    raw,
                )

        created_at = generation.created_at
        if created_at.tzinfo is None:
            return created_at.replace(tzinfo=timezone.utc)
        return created_at.astimezone(timezone.utc)

    @classmethod
    async def _expire_stuck_generations(cls) -> None:
        hard_timeout = max(0, int(settings.generation_hard_timeout_seconds))
        if hard_timeout <= 0:
            return

        cutoff = utcnow() - timedelta(seconds=hard_timeout)
        async with SessionFactory() as session:
            ids = list(
                (
                    await session.scalars(
                        select(Generation.id)
                        .where(
                            Generation.status.in_(("generating", "submitting")),
                            Generation.created_at < cutoff,
                        )
                        .order_by(Generation.created_at.asc())
                        .limit(settings.generation_recovery_batch_size)
                    )
                ).all()
            )

        for generation_id in ids:
            async with SessionFactory() as session:
                generation = await session.get(Generation, generation_id)
                if generation is None or generation.status not in {"generating", "submitting"}:
                    continue
                if cls._provider_started_at(generation) >= cutoff:
                    continue
                message = (
                    "Kie generation exceeded hard lifetime "
                    f"of {settings.generation_hard_timeout_seconds} seconds"
                )
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
                    logger.exception("Kie reconciliation failed for %s", generation_id)
