from __future__ import annotations

import random
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import SessionFactory
from app.main import app
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


@pytest.mark.asyncio
async def test_language_patch_api_preserves_other_preferences() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        user_id = user.id
        await ProfilePreferenceService.update(
            session,
            user_id=user_id,
            ui_language="ru",
            notifications_enabled=False,
            marketing_notifications=False,
            profile_discoverable=True,
        )
        await session.commit()

    async def authenticated_user():  # type: ignore[no-untyped-def]
        return SimpleNamespace(id=user_id)

    app.dependency_overrides[get_current_user] = authenticated_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                "/api/v1/me/preferences/language",
                json={"ui_language": "en"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    assert response.json() == {
        "ui_language": "en",
        "notifications_enabled": False,
        "marketing_notifications": False,
        "profile_discoverable": True,
    }
    async with SessionFactory() as session:
        stored = await ProfilePreferenceService.get_or_create(session, user_id)
        assert stored.ui_language == "en"
        assert stored.notifications_enabled is False
        assert stored.marketing_notifications is False
        assert stored.profile_discoverable is True


@pytest.mark.asyncio
async def test_language_patch_api_rejects_unknown_language_without_mutation() -> None:
    async with SessionFactory() as session:
        user = await _user(session)
        user_id = user.id

    async def authenticated_user():  # type: ignore[no-untyped-def]
        return SimpleNamespace(id=user_id)

    app.dependency_overrides[get_current_user] = authenticated_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.patch(
                "/api/v1/me/preferences/language",
                json={"ui_language": "de"},
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 422
    async with SessionFactory() as session:
        stored = await ProfilePreferenceService.get_or_create(session, user_id)
        assert stored.ui_language == "auto"
