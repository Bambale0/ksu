from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import cast, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminTrend
from app.db.models import Generation
from app.db.reference_models import TemplateAudioReference, UserPreset, UserReference

logger = logging.getLogger(__name__)


class TemplateAudioService:
    @staticmethod
    async def lock(session: AsyncSession) -> None:
        # Serialize template saves, legacy promotion and disposal, until commit.
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('ksu:template-audio'))"))

    @classmethod
    async def pin_recipe(cls, session: AsyncSession, parameters: dict[str, Any]) -> None:
        urls = parameters.get('reference_audio_urls') or []
        if not urls:
            return
        await cls.lock(session)
        for url in dict.fromkeys(urls):
            durable = await session.scalar(select(TemplateAudioReference).where(TemplateAudioReference.source_url == url))
            if durable is not None:
                if durable.status != 'ready':
                    raise ValueError('Template audio was removed; upload it again')
                continue
            legacy = await session.scalar(select(UserReference).where(
                UserReference.source_url == url, UserReference.kind == 'audio',
                UserReference.status == 'ready', UserReference.probe_status == 'ready',
                UserReference.duration_ms > 0,
            ).order_by(UserReference.created_at.desc()).limit(1).with_for_update())
            if legacy is None:
                raise ValueError('Template audio must be uploaded and verified before saving')
            session.add(TemplateAudioReference(
                source_url=url, uploaded_by=legacy.user_id, status='ready',
                original_filename=legacy.original_filename, content_type=legacy.content_type,
                size_bytes=legacy.size_bytes, duration_ms=legacy.duration_ms, probe_status=legacy.probe_status,
            ))
        await session.flush()

    @classmethod
    async def discard(cls, session: AsyncSession, reference_id: uuid.UUID) -> TemplateAudioReference:
        """Tombstone unused audio; never delete bytes shared with personal/history data."""
        await cls.lock(session)
        row = await session.scalar(select(TemplateAudioReference).where(
            TemplateAudioReference.id == reference_id,
        ).with_for_update())
        if row is None:
            raise LookupError('Template audio not found')
        url = row.source_url
        # Hidden templates and duplicates count too. History is retained for reuse.
        recipe = {'parameters': {'reference_audio_urls': [url]}}
        parameters = {'reference_audio_urls': [url]}
        for model, column, contains in (
            (AdminTrend, AdminTrend.payload, recipe),
            (Generation, Generation.parameters, parameters),
            (UserPreset, UserPreset.parameters, parameters),
        ):
            if await session.scalar(select(model.id).where(cast(column, JSONB).contains(contains)).limit(1)):
                raise ValueError('Audio is still used by a template, generation or preset')
        row.status = 'deleted'
        await session.flush()
        logger.info('template_audio_discarded reference_id=%s', row.id)
        return row
