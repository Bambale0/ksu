from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import cast, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminTrend
from app.db.models import Generation
from app.db.reference_models import TemplateAudioReference, UserPreset, UserReference

class TemplateAudioService:
    @staticmethod
    def audio_urls(parameters: Any) -> list[str]:
        """Collect URL values from audio fields, including nested model elements."""
        def strings(value: Any) -> list[str]:
            if isinstance(value, str):
                return [value] if value else []
            if isinstance(value, list):
                return [url for item in value for url in strings(item)]
            if isinstance(value, dict):
                return [url for item in value.values() for url in strings(item)]
            return []

        if isinstance(parameters, list):
            return list(dict.fromkeys(url for item in parameters for url in TemplateAudioService.audio_urls(item)))
        if not isinstance(parameters, dict):
            return []
        urls = []
        for name, value in parameters.items():
            if "audio" in name and (name.endswith("_url") or name.endswith("_urls")):
                urls.extend(strings(value))
            elif isinstance(value, (dict, list)):
                urls.extend(TemplateAudioService.audio_urls(value))
        return list(dict.fromkeys(urls))

    @classmethod
    async def protect_parameters(cls, session: AsyncSession, parameters: dict[str, Any]) -> list[TemplateAudioReference]:
        urls = cls.audio_urls(parameters)
        if not urls:
            return []
        rows = list((await session.scalars(select(TemplateAudioReference).where(
            TemplateAudioReference.source_url.in_(urls),
        ).order_by(TemplateAudioReference.id).with_for_update(read=True).execution_options(populate_existing=True))).all())
        if any(row.status != 'ready' for row in rows):
            raise ValueError('Template audio was removed; upload it again')
        return rows

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
            durable = await session.scalar(select(TemplateAudioReference).where(TemplateAudioReference.source_url == url).execution_options(populate_existing=True))
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
        for model, column in (
            (AdminTrend, AdminTrend.payload),
            (Generation, Generation.parameters),
            (UserPreset, UserPreset.parameters),
        ):
            # Any nested occurrence counts, regardless of provider field spelling.
            used = func.jsonb_path_exists(
                cast(column, JSONB), cast('$.** ? (@ == $url)', JSONPATH),
                func.jsonb_build_object('url', url),
            )
            if await session.scalar(select(model.id).where(used).limit(1)):
                raise ValueError('Audio is still used by a template, generation or preset')
        if await session.scalar(select(UserReference.id).where(
            UserReference.source_url == url, UserReference.status == 'ready',
        ).limit(1)):
            raise ValueError('Audio is still used by personal reference memory')
        row.status = 'deleted'
        await session.flush()
        return row
