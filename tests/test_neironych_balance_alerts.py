from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.api.admin_deps import get_admin_context_base
from app.core.config import settings
from app.db.admin_models import AdminCommand, AdminRuntimeSetting
from app.db.models import AdminAccount, AdminSession, Notification, User
from app.db.notification_models import NotificationDelivery
from app.db.session import SessionFactory
from app.main import app
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

@pytest.mark.asyncio
@pytest.mark.parametrize("untrusted", [
    "-1e999999999",
    "1e999999999",
    "-1e-999999999",
    "9" * 200,
    "999999999999999999.00",
    "0.00000000001",
])
async def test_balance_untrusted_decimal_cannot_expand_into_unbounded_telegram_text(
    monkeypatch: pytest.MonkeyPatch, untrusted: str,
) -> None:
    monkeypatch.setattr(settings, "neironych_api_base_url", "https://neironych.example")
    monkeypatch.setattr(settings, "neironych_api_key", "testing-partner-secret")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
            "partner_id": "test-owned-partner",
            "balance_rub": untrusted,
            "available_balance_rub": "0.00",
        }))
    ) as client:
        with pytest.raises(NeironychBalanceResponseError):
            await NeironychBalanceAlertService.fetch(client=client)


@pytest.mark.asyncio
async def test_revoked_bootstrap_owner_cannot_read_or_receive_pending_balance_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    from app.api.v1.notifications import (
        list_notifications,
        mark_all_notifications_read,
        mark_notification_read,
    )
    from app.workers.notifications import _process_delivery
    from test_notification_delivery import FakeBot

    owner_tg = 99300000000 + (uuid4().int % 1000000)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(owner_tg))
    async with SessionFactory() as session:
        user = User(telegram_id=owner_tg, first_name="RevocableOwner")
        session.add(user)
        await session.flush()
        account = AdminAccount(user_id=user.id, role="owner", is_active=True)
        session.add(account)
        await session.flush()
        assert await NeironychBalanceAlertService.enqueue(
            session, NeironychBalanceSnapshot(Decimal("999.00"), Decimal("999.00"))
        ) == 1
        await session.commit()
        notifications_before = await list_notifications(
            user=user, session=session, unread_only=False, limit=50, offset=0
        )
        assert len(notifications_before["items"]) == 1
        notification = await session.scalar(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.kind == "neironych_balance_low",
            )
        )
        delivery = await session.scalar(
            select(NotificationDelivery).where(NotificationDelivery.notification_id == notification.id)
        )
        delivery.status = "sending"
        delivery.attempts = 1
        notice_id = notification.id
        delivery_id = delivery.id
        account.role = "admin"
        await session.commit()

        after = await list_notifications(
            user=user, session=session, unread_only=False, limit=50, offset=0
        )
        assert after["items"] == []
        assert after["unread_count"] == 0
        from app.services.account_profile import AccountProfileService

        overview = await AccountProfileService.overview(session, user)
        assert overview["notifications"]["unread"] == 0
        with pytest.raises(HTTPException) as exc:
            await mark_notification_read(notification_id=notice_id, user=user, session=session)
        assert exc.value.status_code == 404
        assert (await mark_all_notifications_read(user=user, session=session))["updated"] == 0

    bot = FakeBot()
    await _process_delivery(bot, delivery_id)
    assert not bot.calls
    async with SessionFactory() as session:
        updated = await session.get(NotificationDelivery, delivery_id)
        assert updated.status == "suppressed"
        assert updated.last_error == "owner_authorization_revoked"


@pytest.mark.asyncio
async def test_concurrent_pollers_sample_provider_in_transaction_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    owner_tg = 99400000000 + (uuid4().int % 1000000)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(owner_tg))
    async with SessionFactory() as session:
        owner = User(telegram_id=owner_tg, first_name="OrderedSamplingOwner")
        session.add(owner)
        await session.flush()
        session.add(AdminAccount(user_id=owner.id, role="owner", is_active=True))
        await session.commit()
        owner_id = owner.id

    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[int] = []

    async def fake_balance_fetch(*, client=None) -> NeironychBalanceSnapshot:
        calls.append(len(calls))
        if len(calls) == 1:
            started.set()
            await release.wait()
            return NeironychBalanceSnapshot(Decimal("999.00"), Decimal("999.00"))
        return NeironychBalanceSnapshot(Decimal("1250.00"), Decimal("1250.00"))

    monkeypatch.setattr(NeironychBalanceAlertService, "fetch", fake_balance_fetch)

    task1 = asyncio.create_task(NeironychBalanceAlertService.poll_once())
    await asyncio.wait_for(started.wait(), timeout=3)
    task2 = asyncio.create_task(NeironychBalanceAlertService.poll_once())
    await asyncio.sleep(0.075)
    assert len(calls) == 1, "Second HTTP call must wait for the first sample and transition"
    release.set()
    assert await asyncio.wait_for(asyncio.gather(task1, task2), timeout=6) == [1, 1]

    async with SessionFactory() as session:
        rows = list((await session.scalars(select(Notification)
            .where(Notification.user_id == owner_id,
                   Notification.kind.in_(["neironych_balance_low", "neironych_balance_recovered"]))
            .order_by(Notification.created_at.asc())
        )).all())
        assert [item.kind for item in rows] == ["neironych_balance_low", "neironych_balance_recovered"]


@pytest.mark.asyncio
async def test_db_runtime_policy_controls_threshold_and_can_disable_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setting_key = f"neironych-balance-alert-{uuid4()}"
    monkeypatch.setattr(
        "app.services.neironych_balance_alerts.BALANCE_ALERT_SETTING_KEY", setting_key
    )
    monkeypatch.setattr("app.services.admin_runtime.BALANCE_ALERT_SETTING_KEY", setting_key)
    owner_tg = 99500000000 + (uuid4().int % 1000000)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(owner_tg))

    async with SessionFactory() as session:
        owner = User(telegram_id=owner_tg, first_name="PolicyOwner")
        session.add(owner)
        await session.flush()
        account = AdminAccount(user_id=owner.id, role="owner", is_active=True)
        session.add(account)
        await session.flush()
        session.add(AdminRuntimeSetting(
            key=setting_key,
            value={"enabled": True, "threshold_rub": "900.00", "revision": 4},
            updated_by_admin_id=account.id,
        ))
        await session.commit()
        owner_id = owner.id

    async with SessionFactory() as session:
        policy = await NeironychBalanceAlertService.policy(session)
        assert policy.enabled is True
        assert policy.threshold_rub == Decimal("900.00")
        assert policy.revision == 4
        assert await NeironychBalanceAlertService.enqueue(
            session, NeironychBalanceSnapshot(Decimal("950.00"), Decimal("950.00"))
        ) == 0
        assert await NeironychBalanceAlertService.enqueue(
            session, NeironychBalanceSnapshot(Decimal("900.00"), Decimal("900.00"))
        ) == 1
        await session.commit()

        row = await session.get(AdminRuntimeSetting, setting_key)
        row.value = {"enabled": False, "threshold_rub": "900.00", "revision": 5}
        await session.commit()
        assert await NeironychBalanceAlertService.enqueue(
            session, NeironychBalanceSnapshot(Decimal("0.00"), Decimal("0.00"))
        ) == 0
        await session.commit()

        notices = list((await session.scalars(select(Notification).where(
            Notification.user_id == owner_id,
            Notification.kind.in_(["neironych_balance_low", "neironych_balance_recovered"]),
        ))).all())
        assert [notice.kind for notice in notices] == ["neironych_balance_low"]


@pytest.mark.asyncio
async def test_admin_api_updates_balance_policy_with_mfa_revision_and_idempotency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setting_key = f"neironych-balance-admin-{uuid4()}"
    monkeypatch.setattr(
        "app.services.neironych_balance_alerts.BALANCE_ALERT_SETTING_KEY", setting_key
    )
    monkeypatch.setattr("app.services.admin_runtime.BALANCE_ALERT_SETTING_KEY", setting_key)
    monkeypatch.setattr(
        settings, "admin_security_key", "test-admin-security-key-0000000000000000000000"
    )
    now = datetime.now(UTC)

    async with SessionFactory() as session:
        user = User(telegram_id=uuid4().int % 10**14, first_name="Balance policy admin")
        session.add(user)
        await session.flush()
        admin = AdminAccount(
            user_id=user.id,
            role="auditor",
            is_active=True,
            mfa_enabled=True,
            permission_overrides={},
        )
        session.add(admin)
        await session.flush()
        admin_session = AdminSession(
            admin_id=admin.id,
            token_hash=uuid4().hex,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=1),
            idle_expires_at=now + timedelta(hours=1),
            mfa_verified=True,
            step_up_until=now + timedelta(minutes=5),
            session_version=1,
        )
        session.add(admin_session)
        await session.commit()
        context = SimpleNamespace(account=admin, session=admin_session, user=user)

        async def authenticated_context():
            return context

        app.dependency_overrides[get_admin_context_base] = authenticated_context
        try:
            path = "/api/v1/admin/runtime/neironych-balance-alert"
            payload = {"enabled": True, "threshold_rub": "875.50", "expected_revision": 1}
            key = f"balance-policy-{uuid4()}"
            headers = {"Idempotency-Key": key, "X-Admin-Confirm": "confirmed"}
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                denied = await client.post(path, json=payload, headers=headers)
                assert denied.status_code == 403

                admin.role = "admin"
                admin_session.step_up_until = None
                await session.commit()
                denied = await client.post(path, json=payload, headers=headers)
                assert denied.status_code == 403 and "step-up" in denied.text

                admin_session.step_up_until = now + timedelta(minutes=5)
                await session.commit()
                denied = await client.post(path, json=payload, headers={"Idempotency-Key": key})
                assert denied.status_code == 403
                invalid = await client.post(
                    path,
                    json={**payload, "threshold_rub": "875.501"},
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                )
                assert invalid.status_code == 422

                first = await client.post(path, json=payload, headers=headers)
                assert first.status_code == 200, first.text
                assert first.json() == {
                    "enabled": True,
                    "threshold_rub": "875.50",
                    "revision": 2,
                    "idempotency_replayed": False,
                }
                replay = await client.post(path, json=payload, headers=headers)
                assert replay.status_code == 200
                assert replay.json()["idempotency_replayed"] is True
                stale = await client.post(
                    path,
                    json=payload,
                    headers=headers | {"Idempotency-Key": str(uuid4())},
                )
                assert stale.status_code == 422
                current = await client.get("/api/v1/admin/runtime")
                assert current.status_code == 200
                assert current.json()[setting_key] == {
                    "enabled": True,
                    "threshold_rub": "875.50",
                    "revision": 2,
                }

            command = await session.scalar(
                select(AdminCommand).where(AdminCommand.idempotency_key == key)
            )
            assert command is not None
            assert command.action == "runtime.neironych_balance_alert"
            assert command.status == "completed"
        finally:
            app.dependency_overrides.pop(get_admin_context_base, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_cash,next_cash", [("999.00", "1250.00"), ("1250.00", "999.00")])
async def test_balance_retry_cannot_deliver_a_superseded_episode(
    monkeypatch: pytest.MonkeyPatch, initial_cash: str, next_cash: str,
) -> None:
    from aiogram.exceptions import TelegramRetryAfter
    from aiogram.methods import SendMessage

    from app.workers.notifications import _process_delivery
    from test_notification_delivery import FakeBot

    owner_tg = 99600000000 + (uuid4().int % 1000000)
    monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", str(owner_tg))
    async with SessionFactory() as session:
        owner = User(telegram_id=owner_tg, first_name="RetryOwner")
        session.add(owner)
        await session.flush()
        session.add(AdminAccount(user_id=owner.id, role="owner", is_active=True))
        await session.commit()
        owner_id = owner.id

    async def enqueue(cash: str):
        async with SessionFactory() as session:
            assert await NeironychBalanceAlertService.enqueue(
                session, NeironychBalanceSnapshot(Decimal(cash), Decimal(cash))
            ) == 1
            await session.commit()
            notice = await session.scalar(
                select(Notification)
                .where(Notification.user_id == owner_id)
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(1)
            )
            delivery = await session.scalar(
                select(NotificationDelivery).where(NotificationDelivery.notification_id == notice.id)
            )
            delivery.status = "sending"
            delivery.attempts = 1
            await session.commit()
            return delivery.id

    if initial_cash == "1250.00":
        await enqueue("999.00")  # A recovery requires a preceding low episode.
    old_id = await enqueue(initial_cash)

    class RateLimitedBot(FakeBot):
        async def send_message(self, **kwargs):
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=owner_tg, text="fake"),
                message="retry",
                retry_after=60,
            )

    await _process_delivery(RateLimitedBot(), old_id)
    async with SessionFactory() as session:
        old = await session.get(NotificationDelivery, old_id)
        assert old.status == "retry"

    new_id = await enqueue(next_cash)
    bot = FakeBot()
    await _process_delivery(bot, new_id)
    assert len(bot.calls) == 1
    async with SessionFactory() as session:
        old = await session.get(NotificationDelivery, old_id)
        old.status = "sending"  # Model a later retry claim after Telegram RetryAfter.
        old.attempts += 1
        await session.commit()
    await _process_delivery(bot, old_id)
    assert len(bot.calls) == 1, "An old retry must not contradict the newer delivered state"
    async with SessionFactory() as session:
        old = await session.get(NotificationDelivery, old_id)
        assert old.status == "suppressed"
        assert old.last_error == "balance_episode_superseded"

