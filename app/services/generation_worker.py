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
from app.services.generation_provider_routing import provider_for_model
from app.services.generation_reliability import GenerationOutboxService, utcnow
from app.services.nexus_generation_provider import NexusGenerationProviderService
from app.services.pinterest_quality_gate import PinterestRepeatQualityGate

logger = logging.getLogger(__name__)


class GenerationWorkerService:
    @staticmethod
    def _target_provider(generation: Generation) -> str:
        model_id = str((generation.parameters or {}).get("_model_id") or "")
        return provider_for_model(model_id)

    @classmethod
    async def _poll_nexus_claim(cls, session, claim, generation: Generation, redis: Redis) -> bool:
        try:
            result = await NexusGenerationProviderService.sync_task(
                session,
                task_id=str(generation.external_id),
                generation_id=generation.id,
            )
        except Exception as exc:
            if AbuseProtectionService.availability_failure(exc):
                await AbuseProtectionService.record_provider_failure(redis, "nexus")
            logger.exception("Nexus reconciliation failed for %s", generation.id)
            await GenerationOutboxService.release(
                session,
                claim.outbox_id,
                error=str(exc),
                delay_seconds=max(1, settings.generation_worker_poll_seconds),
            )
            return True

        await AbuseProtectionService.record_provider_success(redis, "nexus")
        if result is None:
            await GenerationOutboxService.release(
                session,
                claim.outbox_id,
                error="Nexus task has no matching generation",
                delay_seconds=max(1, settings.generation_worker_poll_seconds),
            )
        elif result.status == "succeeded":
            await GenerationOutboxService.complete(session, claim.outbox_id)
        elif result.status == "failed":
            await GenerationOutboxService.fail(
                session,
                claim.outbox_id,
                result.error or "Nexus generation failed",
            )
        else:
            await GenerationOutboxService.release(
                session,
                claim.outbox_id,
                error="Nexus generation is still processing",
                delay_seconds=max(1, settings.generation_worker_poll_seconds),
            )
        return True

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

            target_provider = cls._target_provider(generation)

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
                if target_provider == "nexus" or generation.provider == "nexus":
                    return await cls._poll_nexus_claim(session, claim, generation, redis)
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
                if target_provider == "nexus":
                    # Nexus requests use a stable Idempotency-Key, so an interrupted
                    # create request is safe to retry instead of waiting for a KIE callback.
                    generation.status = "retry"
                    generation.error = "Retrying interrupted Nexus submission idempotently"
                    generation.updated_at = utcnow()
                    await session.commit()
                    await GenerationOutboxService.release(
                        session,
                        claim.outbox_id,
                        error=generation.error,
                        delay_seconds=max(1, settings.generation_worker_poll_seconds),
                    )
                    return True

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
                await AbuseProtectionService.provider_submission_gate(redis, target_provider)
            except ResourcePolicyError as exc:
                await GenerationOutboxService.release(
                    session,
                    claim.outbox_id,
                    error=str(exc),
                    delay_seconds=exc.retry_after,
                )
                return True

            try:
                if target_provider == "nexus":
                    result = await NexusGenerationProviderService.submit(session, generation.id)
                else:
                    result = await GenerationProviderService.submit_kie(session, generation.id)
            except Exception as exc:
                if AbuseProtectionService.availability_failure(exc):
                    await AbuseProtectionService.record_provider_failure(redis, target_provider)
                logger.exception("Generation submission failed: %s", generation.id)
                refreshed = await session.get(Generation, generation.id)
                if refreshed is None:
                    await GenerationOutboxService.fail(
                        session,
                        claim.outbox_id,
                        "Generation disappeared after provider submission error",
                    )
                elif refreshed.status == "succeeded":
                    await GenerationOutboxService.complete(session, claim.outbox_id)
                elif refreshed.status == "failed":
                    await GenerationOutboxService.fail(session, claim.outbox_id, str(exc))
                elif (
                    target_provider == "kie"
                    and refreshed.status == "submitting"
                    and refreshed.external_id is None
                ):
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

            await AbuseProtectionService.record_provider_success(redis, target_provider)
            if result.status == "failed":
                await GenerationOutboxService.fail(
                    session,
                    claim.outbox_id,
                    result.error or "Generation failed",
                )
            elif target_provider == "nexus" and result.status == "generating" and result.external_id:
                await GenerationOutboxService.release(
                    session,
                    claim.outbox_id,
                    error="Nexus generation submitted; polling task",
                    delay_seconds=max(1, settings.generation_worker_poll_seconds),
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
        """Repair queue gaps and reconcile stale/expired provider tasks."""

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
                            Generation.provider == "kie",
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
                    or generation.provider != "kie"
                    or generation.status != "submitting"
                    or generation.external_id is not None
                    or generation.updated_at >= cutoff
                ):
                    continue
                if cls._target_provider(generation) == "nexus":
                    generation.status = "retry"
                    generation.error = "Recovered interrupted Nexus submission"
                    generation.updated_at = utcnow()
                    await session.commit()
                    await GenerationOutboxService.requeue_generation(
                        session,
                        generation.id,
                        reason=generation.error,
                    )
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
                            Generation.provider.in_(("kie", "nexus")),
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
                if (
                    generation is None
                    or generation.provider not in {"kie", "nexus"}
                    or generation.status not in {"generating", "submitting"}
                ):
                    continue
                if cls._provider_started_at(generation) >= cutoff:
                    continue
                label = "Nexus" if generation.provider == "nexus" else "Kie"
                message = (
                    f"{label} generation exceeded hard lifetime "
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
                        select(Generation.id, Generation.external_id, Generation.provider)
                        .where(
                            Generation.provider.in_(("kie", "nexus")),
                            Generation.status == "generating",
                            Generation.external_id.is_not(None),
                            Generation.updated_at < cutoff,
                        )
                        .order_by(Generation.updated_at.asc())
                        .limit(settings.generation_recovery_batch_size)
                    )
                ).all()
            )

        for generation_id, external_id, provider in tasks:
            if not external_id:
                continue
            async with SessionFactory() as session:
                try:
                    if provider == "nexus":
                        await NexusGenerationProviderService.sync_task(
                            session,
                            task_id=str(external_id),
                            generation_id=generation_id,
                        )
                    else:
                        await GenerationProviderService.sync_kie_task(
                            session,
                            task_id=str(external_id),
                            generation_id=generation_id,
                        )
                except Exception:
                    logger.exception("%s reconciliation failed for %s", provider, generation_id)
