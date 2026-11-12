"""Verified, administrator-owned video reference lifetime and validation."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.reference_models import TemplateVideoReference
from app.services.reference_static import ReferenceStaticStorage

# Shared operator-configured Kling 4 video limit, also exposed in model UI.
KLING_VIDEO_MAX_BYTES = settings.kling4_reference_video_max_mb * 1024 * 1024
KLING_VIDEO_MIN_DURATION_MS = 2_000
KLING_VIDEO_MAX_DURATION_MS = 30_000


class TemplateVideoService:
    @staticmethod
    @contextmanager
    def authorized(session: AsyncSession, url: str | None) -> Iterator[None]:
        """Scoped capability. Ordinary personal requests cannot borrow pinned clips."""
        if not url:
            yield
            return
        previous = session.info.get("authorized_template_video_url")
        session.info["authorized_template_video_url"] = url
        try:
            yield
        finally:
            if previous is None:
                session.info.pop("authorized_template_video_url", None)
            else:
                session.info["authorized_template_video_url"] = previous

    @staticmethod
    async def verified(session: AsyncSession, url: str) -> TemplateVideoReference:
        row = await session.scalar(
            select(TemplateVideoReference).where(
                TemplateVideoReference.source_url == url,
            ).with_for_update(read=True).execution_options(populate_existing=True)
        )
        if (
            row is None or row.status != "ready" or row.probe_status != "ready"
            or not row.content_type or not row.content_type.startswith("video/")
            or row.size_bytes is None or not 0 < row.size_bytes <= KLING_VIDEO_MAX_BYTES
            or row.duration_ms is None
            or not KLING_VIDEO_MIN_DURATION_MS <= row.duration_ms <= KLING_VIDEO_MAX_DURATION_MS
            or not ReferenceStaticStorage.local_url_exists(row.source_url)
        ):
            raise ValueError(
                f"Template video must be an available verified 2–30s ROXY upload "
                f"(max {settings.kling4_reference_video_max_mb} MB)"
            )
        return row

    @classmethod
    async def authorized_reference(cls, session: AsyncSession, url: str) -> TemplateVideoReference | None:
        if session.info.get("authorized_template_video_url") != url:
            return None
        return await cls.verified(session, url)
