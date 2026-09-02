from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.media_models import MediaAsset, MediaIngestJob
from app.db.models import Generation
from app.services.media_assets import MediaAssetService
from app.services.music_media import MusicMediaAssetService


class LegacyMediaBackfillService:
    """Queue old successful generations into the correct durable-media pipeline."""

    @staticmethod
    def is_audio_generation(generation: Generation) -> bool:
        params = generation.parameters or {}
        return (
            str(getattr(generation, "kind", "") or "").strip().lower() == "music"
            or str(params.get("_provider_api") or "").strip().lower() == "suno_music"
            or str(params.get("_media_type") or "").strip().lower() == "audio"
            or str(params.get("_model_family") or "").strip().lower() == "suno"
        )

    @staticmethod
    def result_urls(generation: Generation) -> list[str]:
        raw = (generation.parameters or {}).get("_result_urls")
        result_urls = [str(item) for item in raw] if isinstance(raw, list) else []
        if generation.result_url and generation.result_url not in result_urls:
            result_urls.insert(0, generation.result_url)
        return result_urls

    @staticmethod
    def is_misrouted_generic_audio_job(job: MediaIngestJob) -> bool:
        if job.status == "pending":
            return True
        if job.status != "failed":
            return False
        error = str(job.last_error or "").lower()
        return "unsupported media content type: audio/" in error

    @classmethod
    async def repair_audio_generation(
        cls,
        session: AsyncSession,
        generation: Generation,
    ) -> int:
        result_urls = cls.result_urls(generation)
        created = await MusicMediaAssetService.enqueue_results(
            session,
            generation,
            result_urls,
        )
        assets = list(
            (
                await session.scalars(
                    select(MediaAsset)
                    .where(MediaAsset.generation_id == generation.id)
                    .order_by(MediaAsset.ordinal.asc())
                )
            ).all()
        )
        repaired = 0
        now = datetime.now(timezone.utc)
        for asset in assets:
            if asset.status == "ready" and asset.object_key and asset.bucket:
                continue
            job = await session.get(MediaIngestJob, asset.id, with_for_update=True)
            if job is None or not cls.is_misrouted_generic_audio_job(job):
                # Existing audio_pending/audio_processing and genuine audio failures
                # belong to MusicMediaIngestQueue. Do not reset their retry state.
                continue
            asset.status = "audio_pending"
            asset.error = None
            job.status = "audio_pending"
            job.attempts = 0
            job.available_at = now
            job.lease_until = None
            job.completed_at = None
            job.last_error = None
            repaired += 1
        return created + repaired

    @classmethod
    async def ensure(cls, session: AsyncSession, *, limit: int = 100) -> int:
        # First repair audio generations that may already have been claimed by
        # the historical generic image/video backfill. Those rows have a
        # MediaAsset, so a plain "missing asset" scan would never see them again.
        audio_generations = list(
            (
                await session.scalars(
                    select(Generation)
                    .outerjoin(MediaAsset, MediaAsset.generation_id == Generation.id)
                    .where(
                        Generation.status == "succeeded",
                        Generation.kind == "music",
                        Generation.result_url.is_not(None),
                        or_(MediaAsset.id.is_(None), MediaAsset.status != "ready"),
                    )
                    .order_by(Generation.created_at.asc())
                    .limit(limit)
                )
            ).unique().all()
        )

        created = 0
        for generation in audio_generations:
            created += await cls.repair_audio_generation(session, generation)

        # Then backfill every successful generation that has no durable asset at
        # all. The parameter snapshot keeps this compatible with older audio
        # rows whose kind predates the current "music" value.
        generations = list(
            (
                await session.scalars(
                    select(Generation)
                    .outerjoin(MediaAsset, MediaAsset.generation_id == Generation.id)
                    .where(
                        Generation.status == "succeeded",
                        MediaAsset.id.is_(None),
                        Generation.result_url.is_not(None),
                    )
                    .order_by(Generation.created_at.asc())
                    .limit(limit)
                )
            ).all()
        )

        for generation in generations:
            result_urls = cls.result_urls(generation)
            if cls.is_audio_generation(generation):
                created += await MusicMediaAssetService.enqueue_results(
                    session,
                    generation,
                    result_urls,
                )
            else:
                created += await MediaAssetService.enqueue_results(
                    session,
                    generation,
                    result_urls,
                )

        if audio_generations or generations:
            await session.commit()
        return created
