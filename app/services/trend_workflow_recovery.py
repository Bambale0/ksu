"""Conservative, idempotent reconciliation of persisted workflow step states.

Only persist terminal states backed by a terminal generation and a verified
ready media row. Never create a generation, charge ROX or start step two.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.media_models import MediaAsset
from app.db.models import Generation
from app.db.trend_workflow_models import TrendWorkflowRun, TrendWorkflowStep

logger = logging.getLogger(__name__)


class TrendWorkflowRecoveryService:
    @staticmethod
    async def reconcile_once(session: AsyncSession, *, limit: int = 50) -> dict[str, int]:
        if not 1 <= limit <= 100:
            raise ValueError("Workflow recovery limit must be between 1 and 100")
        # Rows only, not full workflow objects, are locked. Use SKIP LOCKED
        # so concurrent user retries never race this background reconciler.
        pairs = list((await session.execute(
            select(TrendWorkflowStep, Generation)
            .join(Generation, TrendWorkflowStep.generation_id == Generation.id)
            .where(
                TrendWorkflowStep.status.in_(("queued", "running")),
                Generation.status.in_(("succeeded", "failed")),
            )
            .order_by(TrendWorkflowStep.updated_at.asc(), TrendWorkflowStep.id.asc())
            .limit(limit)
            .with_for_update(of=TrendWorkflowStep, skip_locked=True)
        )).all())
        result = {"inspected": len(pairs), "ready": 0, "failed": 0, "deferred": 0}
        for step, generation in pairs:
            run = await session.get(TrendWorkflowRun, step.workflow_id)
            if run is None or generation.user_id != run.user_id:
                result["deferred"] += 1
                continue
            if generation.status == "failed":
                step.status = "failed"
                # The persisted run must not look active after a terminal
                # generation failure. Explicit user retries may transition
                # it back to running through TrendWorkflowService.run_step.
                # Never retry or charge automatically in this reconciler.
                if run.status == "running":
                    run.status = "failed"
                # Keep detailed provider errors only in their existing
                # generation record; do not duplicate secrets in logs.
                result["failed"] += 1
                continue
            # Never mark a step ready solely because generation succeeded.
            # The file must have been ingested into owned storage.
            required_type = "image/%" if step.kind == "image" else "video/%"
            asset = await session.scalar(
                select(MediaAsset.id)
                .where(
                    MediaAsset.generation_id == generation.id,
                    MediaAsset.user_id == run.user_id,
                    MediaAsset.status == "ready",
                    MediaAsset.bucket.is_not(None),
                    MediaAsset.object_key.is_not(None),
                    MediaAsset.content_type.like(required_type),
                )
                .order_by(MediaAsset.ordinal.asc())
                .limit(1)
            )
            if asset is None:
                result["deferred"] += 1
                continue
            step.status = "ready"
            result["ready"] += 1
            # Do not start video or infer user's consent from a ready photo.
            # Keep run status in sync only when no competing video step exists.
            if step.kind == "video":
                run.status = "completed"
            elif run.status == "running":
                following = await session.scalar(
                    select(TrendWorkflowStep.id).where(
                        TrendWorkflowStep.workflow_id == run.id,
                        TrendWorkflowStep.ordinal > step.ordinal,
                        TrendWorkflowStep.status == "pending",
                    ).limit(1)
                )
                if following is not None:
                    run.status = "step1_ready"
        if result["ready"] or result["failed"]:
            await session.commit()
            logger.info(
                "Trend workflow recovery reconciled ready=%s failed=%s deferred=%s",
                result["ready"], result["failed"], result["deferred"],
            )
        return result