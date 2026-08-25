from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.profile_models import UserPreference


class ProfilePreferenceService:
    ALLOWED_LANGUAGES = {"auto", "ru", "en"}

    @staticmethod
    async def get_or_create(session: AsyncSession, user_id: uuid.UUID) -> UserPreference:
        preference = await session.get(UserPreference, user_id)
        if preference is not None:
            return preference

        # Mini App boot requests /me, profile and notification data in parallel.
        # A plain SELECT -> INSERT races for a fresh account, so let PostgreSQL
        # arbitrate the singleton row without turning the losing request into 500.
        statement = (
            insert(UserPreference)
            .values(
                user_id=user_id,
                ui_language="auto",
                notifications_enabled=True,
                marketing_notifications=False,
                profile_discoverable=False,
            )
            .on_conflict_do_nothing(index_elements=[UserPreference.user_id])
        )
        await session.execute(statement)
        await session.flush()
        # Do not expire the whole identity map here: /me still owns the authenticated
        # User object in this session, and expire_all() makes simple scalar access
        # trigger implicit async I/O (MissingGreenlet) in the response serializer.
        preference = await session.get(UserPreference, user_id)
        if preference is None:
            raise RuntimeError("Unable to initialize user preferences")
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
