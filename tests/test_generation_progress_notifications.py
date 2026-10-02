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


@pytest.mark.asyncio
async def test_progress_uncertain_is_honest_and_normal_ticks_do_not_exhaust_retries() -> None:
    generation_id, delivery_id = await progress_fixture()
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        generation.status = "submitting"
        generation.parameters = {**generation.parameters, "_submission_uncertain": True}
        await session.commit()
    bot = ProgressBot()
    for index in range(12):
        if index:
            await claim_again(delivery_id)
        await _process_delivery(bot, delivery_id)
    assert len(bot.sent) == 1 and len(bot.edited) == 11
    assert "Проверяем результат" in bot.edited[-1]["text"]
    assert "%" not in bot.edited[-1]["text"]
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        generation = await session.get(Generation, generation_id)
        assert delivery.status == "retry" and delivery.attempts == 0
        assert generation.status == "submitting"
        assert generation.parameters["_submission_uncertain"] is True
        assert generation.cost_rox == Decimal("25")


@pytest.mark.asyncio
async def test_progress_retry_after_preserves_anchor_and_retry_budget() -> None:
    from datetime import UTC, datetime, timedelta
    from aiogram.exceptions import TelegramRetryAfter
    from aiogram.methods import EditMessageText

    _generation_id, delivery_id = await progress_fixture()
    bot = ProgressBot()
    await _process_delivery(bot, delivery_id)

    async def rate_limited(**kwargs):
        raise TelegramRetryAfter(
            method=EditMessageText(chat_id=kwargs["chat_id"], text=kwargs["text"]),
            message="Too Many Requests", retry_after=45,
        )

    bot.edit_message_text = rate_limited
    before = datetime.now(UTC)
    await claim_again(delivery_id)
    await _process_delivery(bot, delivery_id)
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery.status == "retry"
        assert delivery.external_message_id == "810"
        assert delivery.attempts == 0
        assert delivery.available_at >= before + timedelta(seconds=45)
    assert len(bot.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [
    ("message is not modified", "retry"),
    ("message to edit not found", "undeliverable"),
    ("message can't be edited", "undeliverable"),
])
async def test_progress_edit_errors_never_replace_the_message(error: str, expected: str) -> None:
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import EditMessageText

    _generation_id, delivery_id = await progress_fixture()
    bot = ProgressBot()
    await _process_delivery(bot, delivery_id)

    async def bad_request(**kwargs):
        raise TelegramBadRequest(
            method=EditMessageText(chat_id=kwargs["chat_id"], text=kwargs["text"]),
            message=error,
        )

    bot.edit_message_text = bad_request
    await claim_again(delivery_id)
    await _process_delivery(bot, delivery_id)
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery.status == expected
        assert delivery.external_message_id == "810"
    assert len(bot.sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("blocker", ["inactive", "preferences", "owner"])
async def test_progress_respects_recipient_and_authorization(blocker: str) -> None:
    from app.db.profile_models import UserPreference

    generation_id, delivery_id = await progress_fixture()
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        user = await session.get(User, generation.user_id)
        if blocker == "inactive":
            user.is_active = False
        elif blocker == "preferences":
            session.add(UserPreference(user_id=user.id, notifications_enabled=False))
        else:
            other = User(telegram_id=961000000000000 + uuid.uuid4().int % 100000000)
            session.add(other)
            await session.flush()
            delivery = await session.get(NotificationDelivery, delivery_id)
            notification = await session.get(Notification, delivery.notification_id)
            notification.user_id = other.id
        await session.commit()
    bot = ProgressBot()
    await _process_delivery(bot, delivery_id)
    assert bot.sent == [] and bot.edited == []
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery.status in {"failed", "undeliverable", "suppressed"}


@pytest.mark.asyncio
async def test_two_workers_cannot_send_two_progress_anchors() -> None:
    import asyncio

    _generation_id, delivery_id = await progress_fixture()
    bot = ProgressBot()
    await asyncio.gather(_process_delivery(bot, delivery_id), _process_delivery(bot, delivery_id))
    assert len(bot.sent) == 1


@pytest.mark.asyncio
async def test_provider_completion_during_edit_is_not_overwritten() -> None:
    generation_id, delivery_id = await progress_fixture()
    bot = ProgressBot()
    await _process_delivery(bot, delivery_id)
    original_edit = bot.edit_message_text

    async def complete_during_edit(**kwargs):
        async with SessionFactory() as session:
            generation = await session.get(Generation, generation_id)
            generation.status = "failed"
            generation.error = "Provider terminal error"
            await session.commit()
        return await original_edit(**kwargs)

    bot.edit_message_text = complete_during_edit
    await claim_again(delivery_id)
    await _process_delivery(bot, delivery_id)
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        assert generation.status == "failed"
        assert generation.error == "Provider terminal error"
    bot.edit_message_text = original_edit
    await claim_again(delivery_id)
    await _process_delivery(bot, delivery_id)
    assert "Не удалось" in bot.edited[-1]["text"]


@pytest.mark.asyncio
async def test_progress_admission_is_atomic_and_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import AsyncMock
    from sqlalchemy import func
    from app.core.config import settings
    from app.db.models import WalletTransaction
    from app.services.generations import GenerationService
    from app.services.generation_progress import enqueue_generation_progress
    from app.services.wallet import WalletService

    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    async with SessionFactory() as session:
        user = User(telegram_id=962000000000000 + uuid.uuid4().int % 100000000)
        session.add(user)
        await session.flush()
        await WalletService.credit(
            session, user_id=user.id, amount=Decimal("1000"), kind="test_seed",
            reference_type="test", reference_id=str(user.id),
            idempotency_key=f"progress-seed:{user.id}",
        )
        await session.commit()
        generations = await GenerationService.create_many(
            session, AsyncMock(), user_id=user.id, model_id="nano-banana-pro",
            prompt="A mountain landscape", parameters={"aspect_ratio": "1:1"}, quantity=2,
        )
        for generation in generations:
            await enqueue_generation_progress(session, generation)
            await enqueue_generation_progress(session, generation)
        await session.commit()
        notes = list((await session.scalars(select(Notification).where(
            Notification.user_id == user.id, Notification.kind == "generation_progress",
        ))).all())
        assert {note.generation_id for note in notes} == {g.id for g in generations}
        assert len(notes) == 2 and all(note.is_read for note in notes)
        deliveries = await session.scalar(select(func.count()).select_from(NotificationDelivery).where(
            NotificationDelivery.notification_id.in_([n.id for n in notes]),
        ))
        assert deliveries == 2
        charges = await session.scalar(select(func.count()).select_from(WalletTransaction).where(
            WalletTransaction.user_id == user.id, WalletTransaction.kind == "generation",
        ))
        assert charges == 2
        # Admission failures roll back progress together with the uncommitted generation.
        pending_id = uuid.uuid4()
        pending = Generation(id=pending_id, user_id=user.id, kind="image", status="queued",
                             prompt="Rollback", cost_rox=Decimal("0"))
        session.add(pending)
        await session.flush()
        await enqueue_generation_progress(session, pending)
        await session.rollback()
    async with SessionFactory() as session:
        assert await session.get(Generation, pending_id) is None
        assert await session.scalar(select(Notification.id).where(
            Notification.generation_id == pending_id,
        )) is None


@pytest.mark.asyncio
async def test_progress_is_hidden_from_notification_api() -> None:
    from fastapi import HTTPException
    from app.api.v1.notifications import list_notifications, mark_notification_read

    generation_id, delivery_id = await progress_fixture()
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        user = await session.get(User, generation.user_id)
        delivery = await session.get(NotificationDelivery, delivery_id)
        result = await list_notifications(user=user, session=session, unread_only=False, limit=50, offset=0)
        assert result["items"] == [] and result["unread_count"] == 0
        with pytest.raises(HTTPException) as denied:
            await mark_notification_read(delivery.notification_id, user=user, session=session)
        assert denied.value.status_code == 404


def test_progress_renderer_escapes_title_and_handles_clock_skew() -> None:
    from datetime import UTC, datetime, timedelta
    from app.services.generation_progress import progress_text
    from app.workers.notifications import _generation_failure_text, _generation_success_text

    now = datetime(2026, 10, 2, 10, 0, tzinfo=UTC)
    generation = Generation(
        id=uuid.uuid4(), kind="image", status="queued", cost_rox=Decimal("0"),
        created_at=now + timedelta(seconds=30),
        parameters={"_model_title": "<b>Title & name</b>", "_model_id": "nano-banana-pro"},
    )
    text = progress_text(generation, now=now)
    assert "&lt;b&gt;Title &amp; name&lt;/b&gt;" in text
    assert "Прошло: 00:00" in text and "%" not in text
    generation.created_at = now - timedelta(seconds=80)
    assert "Прошло: 01:20" in progress_text(generation, now=now)
    assert str(generation.id) in _generation_success_text(generation, result_count=1)
    assert str(generation.id) in _generation_failure_text(generation)


@pytest.mark.asyncio
async def test_disable_progress_finishes_existing_anchor_without_new_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    _generation_id, delivery_id = await progress_fixture()
    bot = ProgressBot()
    await _process_delivery(bot, delivery_id)
    monkeypatch.setattr(settings, "telegram_generation_progress_enabled", False)
    await claim_again(delivery_id)
    await _process_delivery(bot, delivery_id)
    assert len(bot.sent) == 1 and "Автообновление отключено" in bot.edited[-1]["text"]
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery.status == "sent"


@pytest.mark.asyncio
async def test_progress_uuid_survives_the_production_log_formatter(caplog: pytest.LogCaptureFixture) -> None:
    import json
    import logging
    from app.core.logging import JsonFormatter

    generation_id, delivery_id = await progress_fixture()
    with caplog.at_level(logging.INFO, logger="app.services.generation_progress"):
        await _process_delivery(ProgressBot(), delivery_id)
    records = [r for r in caplog.records if r.name == "app.services.generation_progress"]
    assert records
    rendered = json.loads(JsonFormatter().format(records[-1]))
    assert str(generation_id) in rendered["message"]
    assert str(delivery_id) in rendered["message"]
    assert "Private prompt" not in rendered["message"]
