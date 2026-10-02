from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, Update, User, WriteAccessAllowed

from app.bot.handlers import launcher
from app.services.feed_links import parse_feed_deep_link


def test_plain_referral_bot_fallback_opens_home():
    assert launcher._launcher_route(parse_feed_deep_link("ref_777")) == "home"
    assert launcher._launcher_route(None) == "home"


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type,chat_id,expected_messages", [("private", 999, 1), ("group", -999, 0), ("private", 123, 0)])
async def test_consent_does_not_create_unattributed_user_or_clear_fsm(monkeypatch, chat_type, chat_id, expected_messages):
    # Exercise the actual registered launcher router, before its broad catch-all.
    monkeypatch.setattr(launcher.settings, "public_base_url", "https://example.test")
    dispatcher = Dispatcher(storage=MemoryStorage())
    # A fresh router is reconstructed because aiogram routers have one parent.
    from aiogram import Router
    router = Router()
    router.message.handlers = list(launcher.router.message.handlers)
    dispatcher.include_router(router)
    bot = Bot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk")
    state = dispatcher.fsm.get_context(bot=bot, chat_id=chat_id, user_id=999)
    await state.set_state("generation:editing")
    await state.set_data({"prompt": "keep me"})
    create_user = AsyncMock(side_effect=AssertionError("consent must not register before signed referral"))
    monkeypatch.setattr(launcher.UserService, "get_or_create", create_user)
    answer = AsyncMock(return_value=SimpleNamespace(message_id=12))
    monkeypatch.setattr(Message, "answer", answer)
    session = SimpleNamespace(commit=AsyncMock())
    event = Update(update_id=77, message=Message(
        message_id=11, date=datetime.now(UTC), chat=Chat(id=chat_id, type=chat_type),
        from_user=User(id=999, is_bot=False, first_name="Referral"),
        write_access_allowed=WriteAccessAllowed(from_request=True),
    ))
    try:
        await dispatcher.feed_update(bot, event, session=session)
        create_user.assert_not_awaited()
        assert await state.get_state() == "generation:editing"
        assert await state.get_data() == {"prompt": "keep me"}
        assert answer.await_count == expected_messages
        if expected_messages:
            keyboard = answer.call_args.kwargs["reply_markup"]
            assert "route=home" in keyboard.inline_keyboard[0][0].web_app.url
    finally:
        await dispatcher.storage.close()
        await bot.session.close()
