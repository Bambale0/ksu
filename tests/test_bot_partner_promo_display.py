from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.bot.handlers import start as start_module


@pytest.mark.asyncio
async def test_bot_partner_commission_uses_personal_terms(monkeypatch):
    user = SimpleNamespace(id=uuid4(), telegram_id=123456)
    config = SimpleNamespace(
        welcome_rox=Decimal("5"),
        first_line_percent=Decimal("30"),
        topup_partner_rox=Decimal("10"),
    )
    terms = SimpleNamespace(first_line_percent=Decimal("17.5"))
    monkeypatch.setattr(start_module.UserService, "get_or_create", AsyncMock(return_value=user))
    monkeypatch.setattr(start_module.ReferralService, "stats", AsyncMock(return_value={"first_line": 0, "second_line": 0}))
    monkeypatch.setattr(start_module.PartnerWalletTransferService, "accounting", AsyncMock(return_value={"available": Decimal("0")}))
    monkeypatch.setattr(start_module.PartnerPromoProgramService, "get_config", AsyncMock(return_value=config))
    lookup = AsyncMock(return_value=terms)
    monkeypatch.setattr(start_module.PartnerPromoProgramService, "referral_terms", lookup)
    monkeypatch.setattr(start_module.PartnerService, "referral_link", lambda _: None)
    callback = SimpleNamespace(from_user=object(), answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
    session = object()

    await start_module.referrals_callback(callback, session)

    lookup.assert_awaited_once_with(session, user.id)
    message = callback.message.answer.await_args.args[0]
    assert "17.5% — партнёру" in message
    assert "30% — партнёру" not in message
