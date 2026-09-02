from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.onboarding_models import UserOnboarding


PRODUCT_ONBOARDING_VERSION = "2"


class OnboardingService:
    @staticmethod
    def _safe_external_url(value: str) -> str | None:
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.scheme != "https" or not parsed.netloc:
            return None
        return value

    @staticmethod
    def current_version() -> str:
        configured = settings.onboarding_version.strip()
        # Legacy deployments commonly pin version "1" in .env. That value means
        # the original single-card intro, so roll it forward to the current full
        # product onboarding while preserving explicit future/experiment values.
        if not configured or configured == "1":
            return PRODUCT_ONBOARDING_VERSION
        return configured

    @classmethod
    def _current_version(cls) -> str:
        """Backward-compatible alias for older internal callers."""
        return cls.current_version()

    @classmethod
    async def status(cls, session: AsyncSession, user_id: uuid.UUID) -> dict[str, object]:
        row = await session.get(UserOnboarding, user_id)
        current_version = cls.current_version()
        completed_version = row.completed_version if row else None
        completed = (not settings.onboarding_enabled) or completed_version == current_version
        return {
            "enabled": settings.onboarding_enabled,
            "version": current_version,
            "completed": completed,
            "completed_version": completed_version,
            "completed_at": row.completed_at.isoformat() if row else None,
            "title": settings.onboarding_title,
            "body": settings.onboarding_body,
            "rules_url": cls._safe_external_url(settings.onboarding_rules_url),
            "privacy_url": cls._safe_external_url(settings.onboarding_privacy_url),
        }

    @classmethod
    async def complete(cls, session: AsyncSession, user_id: uuid.UUID) -> UserOnboarding:
        current_version = cls.current_version()
        row = await session.get(UserOnboarding, user_id)
        now = datetime.now(UTC)
        if row is None:
            row = UserOnboarding(
                user_id=user_id,
                completed_version=current_version,
                completed_at=now,
            )
            session.add(row)
        elif row.completed_version != current_version:
            row.completed_version = current_version
            row.completed_at = now
        await session.flush()
        return row

    @classmethod
    async def is_complete(cls, session: AsyncSession, user_id: uuid.UUID) -> bool:
        status = await cls.status(session, user_id)
        return bool(status["completed"])
