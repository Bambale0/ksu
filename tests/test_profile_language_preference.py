from __future__ import annotations

import random

import pytest

from app.db.models import User
from app.db.session import SessionFactory
from app.services.profile_preferences import ProfilePreferenceService


async def _user(session) -> User:  # type: ignore[no-untyped-def]
    row = User(
        telegram_id=random.randint(9_600_000_000_000, 9_699_999_999_999),
        first_name="Preference test",
    )
    session.add(row)
    await session.commit()
    return row


@pytest.mark.asyncio
async def test_atomic_language_update_preserves_other_preferences() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        pref = await ProfilePreferenceService.update(
            session,
            user_id=user.id,
            ui_language="ru",
            notifications_enabled=False,
            marketing_notifications=False,
            profile_discoverable=True,
        )
        await session.commit()
        assert pref.ui_language == "ru"

        updated = await ProfilePreferenceService.update_language(
            session,
            user_id=user.id,
            ui_language="en",
        )
        await session.commit()

        assert updated.ui_language == "en"
        assert updated.notifications_enabled is False
        assert updated.marketing_notifications is False
        assert updated.profile_discoverable is True


@pytest.mark.asyncio
async def test_atomic_language_update_rejects_unknown_language() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        with pytest.raises(ValueError, match="Unsupported interface language"):
            await ProfilePreferenceService.update_language(
                session,
                user_id=user.id,
                ui_language="de",
            )


def test_language_endpoint_is_partial_not_full_replacement() -> None:
    source = open("app/api/v1/me.py", encoding="utf-8").read()
    assert '@router.patch("/preferences/language")' in source
    block = source.split('@router.patch("/preferences/language")', 1)[1].split(
        '@router.get("/transactions")', 1
    )[0]
    assert "ProfilePreferenceService.update_language" in block
    assert "notifications_enabled" not in block
    assert "marketing_notifications" not in block
    assert "profile_discoverable" not in block
