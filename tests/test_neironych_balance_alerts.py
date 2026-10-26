from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import AdminAccount, Notification, User
from app.db.notification_models import NotificationDelivery
from app.db.session import SessionFactory
from app.services.neironych_balance_alerts import (
    NeironychBalanceAlertService,
    NeironychBalanceResponseError,
    NeironychBalanceSnapshot,
)


@pytest.mark.asyncio
async def test_partner_balance_fetch_is_private_readonly_and_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "neironych_api_base_url", "https://neironych.example")
    monkeypatch.setattr(settings, "neironych_api_key", "testing-partner-secret")
    calls = []

    def responder(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://neironych.example/v1/balance"
        assert request.headers.get("authorization") == "Bearer testing-partner-secret"
        return httpx.Response(200, json={
            "partner_id": "test-owned-partner",
            "balance_rub": "999.99",
            "credit_limit_rub": "250.00",
            "available_balance_rub": "1249.99",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
        snapshot = await NeironychBalanceAlertService.fetch(client=client)
    assert snapshot == NeironychBalanceSnapshot(
        cash_rub=Decimal("999.99"), available_rub=Decimal("1249.99")
    )
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"balance_rub": "NaN", "available_balance_rub": "100"},
    {"balance_rub": "Infinity", "available_balance_rub": "100"},
    {"balance_rub": "-Infinity", "available_balance_rub": "100"},
    {"balance_rub": None, "available_balance_rub": "100"},
    {"balance_rub": 5.7, "available_balance_rub": "100"},
    {"balance_rub": "100", "available_balance_rub": None},
    {"balance_rub": "incorrect", "available_balance_rub": "100"},
    {"balance_rub": "100"},
    {"available_balance_rub": "200"},
])
async def test_balance_monitor_rejects_untrustworthy_provider_cash_values(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object],
) -> None:
    monkeypatch.setattr(settings, "neironych_api_base_url", "https://neironych.example")
    monkeypatch.setattr(settings, "neironych_api_key", "testing-partner-secret")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"partner_id": "test-partner", **payload}))
    ) as client:
        with pytest.raises(NeironychBalanceResponseError):
            await NeironychBalanceAlertService.fetch(client=client)


@pytest.mark.asyncio
async def test_balance_fetch_remote_errors_never_fabricate_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "neironych_api_base_url", "https://neironych.example")
    monkeypatch.setattr(settings, "neironych_api_key", "testing-partner-secret")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(401, json={"error": "invalid_api_key"}))
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await NeironychBalanceAlertService.fetch(client=client)
    monkeypatch.setattr(settings, "neironych_api_key", "")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: pytest.fail("unconfigured key must not send HTTP"))
    ) as client:
        with pytest.raises(NeironychBalanceResponseError):
            await NeironychBalanceAlertService.fetch(client=client)


@pytest.mark.asyncio
async def test_only_configured_active_owner_receives_one_per_low_balance_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_tg = 99000000000 + (uuid4().int % 1000000) * 10
    owner_tg = base_tg + 1
    other_admin_tg = base_tg + 2
    other_owner_tg = base_tg + 3
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(owner_tg))
    async with SessionFactory() as session:
        owner = User(telegram_id=owner_tg, first_name="BalanceOwner")
        other_admin = User(telegram_id=other_admin_tg, first_name="UnrelatedAdmin")
        other_owner = User(telegram_id=other_owner_tg, first_name="UnrelatedOwner")
        session.add_all([owner, other_admin, other_owner])
        await session.flush()
        session.add_all([
            AdminAccount(user_id=owner.id, role="owner", is_active=True),
            AdminAccount(user_id=other_admin.id, role="admin", is_active=True),
            AdminAccount(user_id=other_owner.id, role="owner", is_active=True),
        ])
        await session.commit()
        owner_id = owner.id

    async def poll(cash: str) -> int:
        async with SessionFactory() as session:
            result = await NeironychBalanceAlertService.enqueue(
                session,
                NeironychBalanceSnapshot(
                    cash_rub=Decimal(cash), available_rub=Decimal(cash) + Decimal("999"),
                ),
            )
            await session.commit()
            return result

    assert await poll("1010.00") == 0
    assert await poll("1000.00") == 1
    assert await poll("999.99") == 0
    assert await poll("-12.34") == 0
    assert await poll("1000.01") == 1
    assert await poll("1002.00") == 0
    assert await poll("999.00") == 1
    assert await poll("999.00") == 0

    async with SessionFactory() as session:
        notices = list((await session.scalars(
            select(Notification)
            .where(
                Notification.user_id == owner_id,
                Notification.kind.in_(["neironych_balance_low", "neironych_balance_recovered"]),
            )
            .order_by(Notification.created_at.asc())
        )).all())
        assert len(notices) == 3
        assert [item.kind for item in notices] == [
            "neironych_balance_low", "neironych_balance_recovered", "neironych_balance_low"
        ]
        assert all(item.user_id == owner_id for item in notices)
        assert "1 000" in notices[0].body or "1000" in notices[0].body
        assert "1 000" not in notices[0].title or "Нейроныч" in notices[0].title
        deliveries = list((await session.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([item.id for item in notices])
        ))).all())
        assert len(deliveries) == 3
        assert all(item.channel == "telegram" and item.purpose == "transactional" for item in deliveries)


@pytest.mark.asyncio
async def test_inactive_or_unconfigured_owner_never_leaks_provider_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "99300000888")
    async with SessionFactory() as session:
        result = await NeironychBalanceAlertService.enqueue(
            session, NeironychBalanceSnapshot(Decimal("0.00"), Decimal("0.00"))
        )
        await session.commit()
    assert result == 0

@pytest.mark.asyncio
async def test_low_balance_warning_reaches_owner_even_with_personal_notifications_muted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.profile_models import UserPreference
    from app.workers.notifications import _process_delivery
    from test_notification_delivery import FakeBot

    owner_tg = 99100000000 + (uuid4().int % 1000000)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(owner_tg))
    async with SessionFactory() as session:
        owner = User(telegram_id=owner_tg, first_name="MutedOwner")
        session.add(owner)
        await session.flush()
        session.add_all([
            AdminAccount(user_id=owner.id, role="owner", is_active=True),
            UserPreference(user_id=owner.id, notifications_enabled=False),
        ])
        await session.flush()
        count = await NeironychBalanceAlertService.enqueue(
            session, NeironychBalanceSnapshot(Decimal("1000.00"), Decimal("1000.00"))
        )
        assert count == 1
        await session.commit()
        notification = await session.scalar(
            select(Notification)
            .where(Notification.user_id == owner.id, Notification.kind == "neironych_balance_low")
        )
        delivery = await session.scalar(
            select(NotificationDelivery)
            .where(NotificationDelivery.notification_id == notification.id)
        )
        delivery.status = "sending"
        delivery.attempts = 1
        delivery_id = delivery.id
        await session.commit()

    bot = FakeBot()
    await _process_delivery(bot, delivery_id)
    assert len(bot.calls) == 1
    assert bot.calls[0][0] == owner_tg
    assert "Нейроныч" in bot.calls[0][1] and "1000" in bot.calls[0][1]
    async with SessionFactory() as session:
        delivered = await session.get(NotificationDelivery, delivery_id)
        assert delivered.status == "sent"
        assert delivered.external_message_id == "777"


@pytest.mark.asyncio
async def test_concurrent_alert_checks_do_not_queue_duplicate_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    owner_tg = 99200000000 + (uuid4().int % 1000000)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(owner_tg))
    async with SessionFactory() as session:
        owner = User(telegram_id=owner_tg, first_name="ConcurrentOwner")
        session.add(owner)
        await session.flush()
        session.add(AdminAccount(user_id=owner.id, role="owner", is_active=True))
        await session.commit()
        owner_id = owner.id

    async def check() -> int:
        async with SessionFactory() as session:
            result = await NeironychBalanceAlertService.enqueue(
                session, NeironychBalanceSnapshot(Decimal("999.50"), Decimal("999.50"))
            )
            await session.commit()
            return result

    assert sorted(await asyncio.gather(check(), check())) == [0, 1]
    async with SessionFactory() as session:
        count = len(list((await session.scalars(select(Notification).where(
            Notification.user_id == owner_id,
            Notification.kind == "neironych_balance_low",
        ))).all()))
    assert count == 1

