from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.profile_models import UserPreference


class ProfilePreferenceService:
    ALLOWED_LANGUAGES = {"auto", "ru", "en"}

    @staticmethod
    async def get_or_create(session: AsyncSession, user_id: uuid.UUID) -> UserPreference:
        preference = await session.get(UserPreference, user_id)
        if preference is None:
            preference = UserPreference(user_id=user_id)
            session.add(preference)
            await session.flush()
        return preference

    @classmethod
    async def update(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        ui_language: str,
        notifications_enabled: bool,
        marketing_notifications: bool,
        profile_discoverable: bool,
    ) -> UserPreference:
        if ui_language not in cls.ALLOWED_LANGUAGES:
            raise ValueError("Unsupported interface language")
        preference = await cls.get_or_create(session, user_id)
        enabled = bool(notifications_enabled)
        preference.ui_language = ui_language
        preference.notifications_enabled = enabled
        preference.marketing_notifications = bool(marketing_notifications and enabled)
        preference.profile_discoverable = bool(profile_discoverable)
        await session.flush()
        return preference
