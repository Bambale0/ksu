from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.models import Generation, Notification, User
from app.db.notification_models import NotificationDelivery
from app.db.session import SessionFactory
from app.services.notifications import NotificationService
from app.workers.notifications import _process_delivery


class ProgressBot:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.edited: list[dict] = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return SimpleNamespace(message_id=810)

    async def edit_message_text(self, **kwargs):
        self.edited.append(kwargs)
        return SimpleNamespace(message_id=kwargs["message_id"])


async def progress_fixture() -> tuple[uuid.UUID, uuid.UUID]:
    async with SessionFactory() as session:
        user = User(telegram_id=960000000000000 + uuid.uuid4().int % 100000000, first_name="Progress")
        session.add(user)
        await session.flush()
        generation = Generation(
            id=uuid.uuid4(), user_id=user.id, kind="image", status="queued",
            prompt="Private prompt must not appear in progress", cost_rox=Decimal("25"),
            parameters={"_model_id": "nano-banana-pro", "_model_title": "Nano Banana Pro"},
        )
        session.add(generation)
        await session.flush()
        notification = Notification(
            id=uuid.uuid4(), user_id=user.id, generation_id=generation.id,
            kind="generation_progress", title="Генерация", body="", is_read=True,
        )
        session.add(notification)
        await session.flush()
        await NotificationService.enqueue_existing(session, notification_id=notification.id)
        delivery = await session.scalar(select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notification.id,
        ))
        delivery.status = "sending"
        delivery.attempts = 1
        await session.commit()
        return generation.id, delivery.id


async def claim_again(delivery_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        delivery.status = "sending"
        delivery.attempts += 1
        await session.commit()


@pytest.mark.asyncio
async def test_progress_reuses_one_message_and_stops_after_terminal_state() -> None:
    generation_id, delivery_id = await progress_fixture()
    bot = ProgressBot()
    await _process_delivery(bot, delivery_id)
    assert len(bot.sent) == 1
    assert str(generation_id) in bot.sent[0]["text"]
    assert "В очереди" in bot.sent[0]["text"]
    assert "Private prompt" not in bot.sent[0]["text"]
    assert bot.sent[0]["parse_mode"] == "HTML"
    buttons = [button for row in bot.sent[0]["reply_markup"].inline_keyboard for button in row]
    assert any(button.copy_text and button.copy_text.text == str(generation_id) for button in buttons)

    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        generation = await session.get(Generation, generation_id)
        assert delivery.status == "retry"
        assert delivery.external_message_id == "810"
        assert delivery.attempts == 0
        assert generation.telegram_notification_status != "sent"
        generation.status = "generating"
        await session.commit()

    # A new worker/session must recover the saved Telegram message, not send another.
    await claim_again(delivery_id)
    await _process_delivery(bot, delivery_id)
    assert len(bot.sent) == 1
    assert bot.edited[-1]["message_id"] == 810
    assert "Генерируем" in bot.edited[-1]["text"]
    assert str(generation_id) in bot.edited[-1]["text"]

    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        generation.status = "failed"
        await session.commit()
    await claim_again(delivery_id)
    await _process_delivery(bot, delivery_id)
    assert "Не удалось" in bot.edited[-1]["text"]
    assert str(generation_id) in bot.edited[-1]["text"]
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        generation = await session.get(Generation, generation_id)
        assert delivery.status == "sent"
        assert generation.telegram_notification_status != "sent"
    previous = len(bot.edited)
    await _process_delivery(bot, delivery_id)
    assert len(bot.edited) == previous
