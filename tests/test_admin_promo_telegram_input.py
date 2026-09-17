import random
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.bot.handlers.admin import admin_promo_create
from app.db.models import AdminAccount, PromoCode, User
from app.db.session import SessionFactory


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier_kind", ["telegram", "uuid"])
async def test_admin_can_create_partner_promo_with_telegram_id_or_uuid(identifier_kind):
    async with SessionFactory() as session:
        admin_user = User(telegram_id=random.randint(870_000_000_000, 879_999_999_999))
        partner = User(telegram_id=random.randint(860_000_000_000, 869_999_999_999))
        session.add_all([admin_user, partner])
        await session.flush()
        session.add(AdminAccount(user_id=admin_user.id, role="admin", is_active=True))
        await session.commit()
        code = f"ROXY_{uuid.uuid4().hex[:12]}".upper()
        identifier = str(partner.telegram_id if identifier_kind == "telegram" else partner.id)
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=admin_user.telegram_id),
            chat=SimpleNamespace(id=admin_user.telegram_id), message_id=101,
            text=f"{code} {identifier} 500", answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        await admin_promo_create(message, session, state)
        # Replay of the same Telegram update must not create another command.
        await admin_promo_create(message, session, state)
        promo = await session.scalar(select(PromoCode).where(PromoCode.code == code))
        assert promo is not None
        assert promo.partner_user_id == partner.id
        assert promo.max_uses == 500
        assert all(call.args[0].startswith("✅") for call in message.answer.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("text, expected", [
    ("ROXY_123456789_500", "пробелами"),
    ("ROXY invalid 500", "Telegram ID"),
    ("ROXY 123456789 500", "не найден"),
    ("ROXY 123456789 0", "Лимит"),
])
async def test_admin_promo_input_errors_are_actionable_and_keep_state(text, expected):
    async with SessionFactory() as session:
        user = User(telegram_id=random.randint(870_000_000_000, 879_999_999_999))
        session.add(user)
        await session.flush()
        session.add(AdminAccount(user_id=user.id, role="admin", is_active=True))
        await session.commit()
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=user.telegram_id), chat=SimpleNamespace(id=user.telegram_id),
            message_id=102, text=text, answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        await admin_promo_create(message, session, state)
        reply = message.answer.await_args.args[0]
        assert expected in reply
        assert "hexadecimal" not in reply
        state.clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_admin_cannot_create_promo_from_telegram_input():
    async with SessionFactory() as session:
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=123456789), text="ROXY 123456789 500", answer=AsyncMock(),
        )
        state = SimpleNamespace(clear=AsyncMock())
        await admin_promo_create(message, session, state)
        assert "Админ-доступ" in message.answer.await_args.args[0]
        state.clear.assert_awaited_once()
