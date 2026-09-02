from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.media_models import MediaAsset
from app.db.models import Generation
from app.services.media_assets import MediaAssetService
from app.services.music_media import MusicMediaAssetService


class LegacyMediaBackfillService:
    """Queue old successful generations into the correct durable-media pipeline."""

    @staticmethod
    def is_audio_generation(generation: Generation) -> bool:
        params = generation.parameters or {}
        return (
            str(params.get("_provider_api") or "").strip().lower() == "suno_music"
            or str(params.get("_media_type") or "").strip().lower() == "audio"
            or str(params.get("_model_family") or "").strip().lower() == "suno"
        )

    @classmethod
    async def ensure(cls, session: AsyncSession, *, limit: int = 100) -> int:
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

        created = 0
        for generation in generations:
            raw = (generation.parameters or {}).get("_result_urls")
            result_urls = [str(item) for item in raw] if isinstance(raw, list) else []
            if generation.result_url and generation.result_url not in result_urls:
                result_urls.insert(0, generation.result_url)

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

        if generations:
            await session.commit()
        return created
