from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.db.models import Generation, Notification, Payment, SupportMessage, SupportTicket, User
from app.db.notification_models import NotificationDelivery
from app.db.profile_models import UserPreference
from app.db.session import SessionFactory
from app.services.notification_events import register_notification_events
from app.services.notifications import NotificationDeliveryService, NotificationService
from app.workers.notifications import _process_delivery

register_notification_events()


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []
        self.media_calls: list[dict[str, object]] = []

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None):  # type: ignore[no-untyped-def]
        self.calls.append((chat_id, text))
        if reply_markup is not None:
            self.media_calls.append(
                {
                    "method": "message",
                    "chat_id": chat_id,
                    "text": text,
                    "reply_markup": reply_markup,
                }
            )
        return SimpleNamespace(message_id=777)

    async def send_photo(self, *, chat_id: int, photo: str, caption: str, reply_markup=None):  # type: ignore[no-untyped-def]
        self.media_calls.append(
            {
                "method": "photo",
                "chat_id": chat_id,
                "url": photo,
                "caption": caption,
                "reply_markup": reply_markup,
            }
        )
        return SimpleNamespace(message_id=778)

    async def send_video(
        self,
        *,
        chat_id: int,
        video: str,
        caption: str,
        reply_markup=None,
        supports_streaming: bool = False,
    ):  # type: ignore[no-untyped-def]
        self.media_calls.append(
            {
                "method": "video",
                "chat_id": chat_id,
                "url": video,
                "caption": caption,
                "reply_markup": reply_markup,
                "supports_streaming": supports_streaming,
            }
        )
        return SimpleNamespace(message_id=779)

    async def send_audio(self, *, chat_id: int, audio: str, caption: str, reply_markup=None):  # type: ignore[no-untyped-def]
        self.media_calls.append(
            {
                "method": "audio",
                "chat_id": chat_id,
                "url": audio,
                "caption": caption,
                "reply_markup": reply_markup,
            }
        )
        return SimpleNamespace(message_id=780)


@pytest.mark.asyncio
async def test_notification_service_creates_one_delivery_per_channel() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000001, first_name="Notify")
        session.add(user)
        await session.flush()
        notification = await NotificationService.create(
            session,
            user_id=user.id,
            kind="test",
            title="Тест",
            body="Сообщение",
        )
        await NotificationService.enqueue_existing(session, notification_id=notification.id)
        await session.commit()

        count = await session.scalar(
            select(func.count()).select_from(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert int(count or 0) == 1
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert delivery is not None
        assert delivery.status == "pending"
        assert delivery.channel == "telegram"


@pytest.mark.asyncio
async def test_generation_success_transition_queues_domain_linked_delivery() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000008, first_name="Generation")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="image",
            status="queued",
            prompt="portrait",
            cost_rox=Decimal("40.00"),
            parameters={"_model_id": "nano-banana-pro"},
        )
        session.add(generation)
        await session.commit()

        generation.status = "succeeded"
        generation.result_url = "https://cdn.example/result.png"
        generation.parameters = {
            **generation.parameters,
            "_result_urls": ["https://cdn.example/result.png"],
        }
        await session.commit()

        notification = await session.get(Notification, generation.id)
        assert notification is not None
        assert notification.kind == "generation_succeeded"
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == generation.id
            )
        )
        assert delivery is not None
        assert delivery.status == "pending"
        assert generation.telegram_notification_status == "pending"
        assert generation.telegram_notification_sent_at is None
        assert generation.telegram_message_id is None


@pytest.mark.asyncio
async def test_generation_result_is_delivered_as_media_and_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    bot = FakeBot()
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000009, first_name="Media")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="image",
            status="queued",
            prompt="portrait",
            cost_rox=Decimal("40.00"),
            parameters={"_model_id": "nano-banana-pro"},
        )
        session.add(generation)
        await session.commit()
        generation.status = "succeeded"
        generation.result_url = "https://cdn.example/result.png"
        generation.parameters = {
            **generation.parameters,
            "_result_urls": ["https://cdn.example/result.png"],
        }
        await session.commit()

        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == generation.id
            )
        )
        assert delivery is not None
        delivery.status = "sending"
        delivery.attempts = 1
        generation.telegram_notification_status = "sending"
        await session.commit()
        delivery_id = delivery.id
        generation_id = generation.id

    await _process_delivery(bot, delivery_id)

    assert len(bot.media_calls) == 1
    media_call = bot.media_calls[0]
    assert media_call["method"] == "photo"
    assert media_call["url"] == "https://cdn.example/result.png"
    caption = str(media_call["caption"])
    assert "✅ Генерация завершена" in caption
    assert "NanoBanana PRO" in caption
    assert "1 фото" in caption
    assert "40 ROX" in caption
    keyboard = media_call["reply_markup"]
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "📥 Скачать оригинал" in labels
    assert "🚀 Открыть в ROXY" in labels

    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        generation = await session.get(Generation, generation_id)
        assert delivery is not None
        assert generation is not None
        assert delivery.status == "sent"
        assert delivery.external_message_id == "778"
        assert generation.telegram_notification_status == "sent"
        assert generation.telegram_notification_sent_at is not None
        assert generation.telegram_message_id == "778"


@pytest.mark.asyncio
async def test_generation_delivery_guard_does_not_send_media_twice() -> None:
    bot = FakeBot()
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000010, first_name="No duplicate")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="video",
            status="queued",
            prompt="clip",
            cost_rox=Decimal("30.00"),
            parameters={"_model_id": "kling-3.0"},
        )
        session.add(generation)
        await session.commit()
        generation.status = "succeeded"
        generation.result_url = "https://cdn.example/result.mp4"
        generation.parameters = {
            **generation.parameters,
            "_result_urls": ["https://cdn.example/result.mp4"],
        }
        await session.commit()

        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == generation.id
            )
        )
        assert delivery is not None
        delivery.status = "sending"
        delivery.attempts = 2
        generation.telegram_notification_status = "sent"
        generation.telegram_message_id = "991"
        generation.telegram_notification_sent_at = generation.updated_at
        await session.commit()
        delivery_id = delivery.id

    await _process_delivery(bot, delivery_id)

    assert bot.media_calls == []
    assert bot.calls == []
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery is not None
        assert delivery.status == "sent"
        assert delivery.external_message_id == "991"


@pytest.mark.asyncio
async def test_payment_success_transition_atomically_creates_inbox_and_outbox() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000002, first_name="Paid")
        session.add(user)
        await session.flush()
        payment = Payment(
            user_id=user.id,
            provider="tbank",
            amount=Decimal("100.00"),
            currency="RUB",
            rox_amount=Decimal("10.00"),
            status="pending",
            payload={},
        )
        session.add(payment)
        await session.commit()

        payment.status = "succeeded"
        await session.commit()

        notification = await session.scalar(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.kind == "payment_succeeded",
            )
        )
        assert notification is not None
        assert "10" in notification.body
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert delivery is not None
        assert delivery.status == "pending"


@pytest.mark.asyncio
async def test_admin_support_reply_creates_user_notification() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000003, first_name="Support user")
        admin_user = User(telegram_id=970000000000004, first_name="Admin")
        session.add_all([user, admin_user])
        await session.flush()
        ticket = SupportTicket(user_id=user.id, topic="payment", status="open")
        session.add(ticket)
        await session.flush()
        session.add(
            SupportMessage(
                ticket_id=ticket.id,
                user_id=admin_user.id,
                is_admin=True,
                body="Ответ оператора",
            )
        )
        await session.commit()

        notification = await session.scalar(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.kind == "support_reply",
            )
        )
        assert notification is not None
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert delivery is not None


@pytest.mark.asyncio
async def test_worker_suppresses_push_when_user_disabled_notifications() -> None:
    bot = FakeBot()
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000005, first_name="Quiet")
        session.add(user)
        await session.flush()
        session.add(UserPreference(user_id=user.id, notifications_enabled=False))
        notification = await NotificationService.create(
            session,
            user_id=user.id,
            kind="quiet",
            title="Не пушить",
            body="Но оставить в inbox",
        )
        await session.commit()
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert delivery is not None
        delivery.status = "sending"
        delivery.attempts = 1
        await session.commit()
        delivery_id = delivery.id

    await _process_delivery(bot, delivery_id)  # type: ignore[arg-type]

    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery is not None
        assert delivery.status == "suppressed"
        assert delivery.last_error == "notifications_disabled"
        assert bot.calls == []
        inbox = await session.scalar(
            select(Notification).where(Notification.id == delivery.notification_id)
        )
        assert inbox is not None


@pytest.mark.asyncio
async def test_worker_marks_success_and_records_telegram_message_id() -> None:
    bot = FakeBot()
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000006, first_name="Push")
        session.add(user)
        await session.flush()
        notification = await NotificationService.create(
            session,
            user_id=user.id,
            kind="push",
            title="Готово",
            body="Результат готов",
        )
        await session.commit()
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert delivery is not None
        delivery.status = "sending"
        delivery.attempts = 1
        await session.commit()
        delivery_id = delivery.id
        telegram_id = user.telegram_id

    await _process_delivery(bot, delivery_id)  # type: ignore[arg-type]

    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery is not None
        assert delivery.status == "sent"
        assert delivery.external_message_id == "777"
        assert delivery.sent_at is not None
    assert bot.calls == [(telegram_id, "Готово\n\nРезультат готов")]


@pytest.mark.asyncio
async def test_retry_becomes_terminal_after_attempt_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "notification_delivery_max_attempts", 2)
    async with SessionFactory() as session:
        user = User(telegram_id=970000000000007, first_name="Retry")
        session.add(user)
        await session.flush()
        notification = await NotificationService.create(
            session,
            user_id=user.id,
            kind="retry",
            title="Retry",
            body="Retry",
        )
        await session.flush()
        delivery = await session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.notification_id == notification.id
            )
        )
        assert delivery is not None
        delivery.status = "sending"
        delivery.attempts = 2
        await NotificationDeliveryService.mark_retry(session, delivery, error="network")
        await session.commit()
        assert delivery.status == "failed"
        assert delivery.last_error == "network"
