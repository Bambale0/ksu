from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from aiogram.types import Chat, Message, Update, User as TelegramUser
from fastapi import FastAPI
import httpx
import pytest

from app.api import deps
from app.api.v1 import me as me_api
from app.bot import middlewares
from app.core.config import settings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chat_type,chat_id,sender_id,expected",
    [("private", 999, 999, 1), ("group", -999, 999, 0),
     ("supergroup", -100999, 999, 0), ("private", 123, 999, 0),
     ("private", 999, 123, 0)],
)
async def test_only_own_private_contact_requeues_delivery(monkeypatch, chat_type, chat_id, sender_id, expected):
    user = SimpleNamespace(id=uuid.uuid4(), is_active=True)
    session = SimpleNamespace(scalar=AsyncMock(return_value=user), commit=AsyncMock(), rollback=AsyncMock())

    @asynccontextmanager
    async def sessions():
        yield session

    monkeypatch.setattr(middlewares, "SessionFactory", sessions)
    recover = AsyncMock(return_value=2)
    monkeypatch.setattr(middlewares.NotificationDeliveryService, "requeue_reachable_user_deliveries", recover)
    identity = TelegramUser(id=999, is_bot=False, first_name="Test")
    event = Update(update_id=41, message=Message(
        message_id=42, date=datetime.now(UTC), chat=Chat(id=chat_id, type=chat_type),
        from_user=TelegramUser(id=sender_id, is_bot=False, first_name="Sender"), text="hello",
    ))
    handler = AsyncMock(return_value="handled")
    assert await middlewares.DatabaseSessionMiddleware()(handler, event, {"event_from_user": identity}) == "handled"
    assert recover.await_count == expected
    assert session.commit.await_count == 1 + expected
    if expected:
        assert recover.call_args.kwargs["user_id"] == user.id
    handler.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("username,expected", [
    ("@changed_bot", "https://t.me/changed_bot?start=connect"), ("", None),
])
async def test_me_exposes_configured_chat_link_without_extra_network(monkeypatch, username, expected):
    monkeypatch.setattr(settings, "bot_username", username)
    user = SimpleNamespace(
        id=uuid.uuid4(), telegram_id=999, username=None, first_name="Test", last_name=None,
        language_code="ru", created_at=datetime.now(UTC), is_active=True,
    )
    session = SimpleNamespace(get=AsyncMock(return_value=None), commit=AsyncMock())
    preference = SimpleNamespace(ui_language="ru", notifications_enabled=True,
                                 marketing_notifications=False, profile_discoverable=False)
    monkeypatch.setattr(me_api.ProfilePreferenceService, "get_or_create", AsyncMock(return_value=preference))
    monkeypatch.setattr(me_api.BillingAccessService, "is_active_admin", AsyncMock(return_value=False))

    async def authenticated_user():
        return user

    async def isolated_session():
        yield session

    app = FastAPI()
    app.include_router(me_api.router, prefix="/api/v1")
    app.dependency_overrides[deps.get_current_user] = authenticated_user
    app.dependency_overrides[deps.get_session] = isolated_session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["bot_chat_link"] == expected
    assert response.json()["telegram_id"] == 999
