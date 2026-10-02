from __future__ import annotations

import html
import logging
import uuid
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Generation, Notification
from app.db.notification_models import NotificationDelivery
from app.services.notifications import NotificationDeliveryService, NotificationService

logger = logging.getLogger(__name__)
GENERATION_PROGRESS_KIND = "generation_progress"
_ACTIVE_STATES = frozenset({"queued", "retry", "submitting", "generating"})
_SPINNER = ("◐", "◓", "◑", "◒")


async def enqueue_generation_progress(session: AsyncSession, generation: Generation) -> None:
    """Add the Telegram status in the admission transaction, without network I/O.

    A deterministic notification identity makes repeated enqueueing harmless.
    Progress owns its delivery message ID, never the final media delivery fields.
    """
    if not settings.telegram_generation_progress_enabled:
        return
    notification_id = uuid.uuid5(generation.id, GENERATION_PROGRESS_KIND)
    await session.execute(
        pg_insert(Notification)
        .values(
            id=notification_id,
            user_id=generation.user_id,
            generation_id=generation.id,
            kind=GENERATION_PROGRESS_KIND,
            title="Статус генерации",
            body="",
            is_read=True,
        )
        .on_conflict_do_nothing(index_elements=[Notification.id])
    )
    await NotificationService.enqueue_existing(session, notification_id=notification_id)


def progress_text(generation: Generation, *, now: datetime | None = None) -> str:
    """Render observed state, not a fabricated percentage or completion estimate."""
    current = now or datetime.now(UTC)
    started = generation.created_at or current
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    elapsed = max(0, int((current - started).total_seconds()))
    minutes, seconds = divmod(elapsed, 60)
    params = generation.parameters or {}
    title = html.escape(str(params.get("_model_title") or "Генерация")[:120])
    identity = f"UUID задачи:\n<code>{generation.id}</code>"
    active = generation.status in _ACTIVE_STATES
    if generation.status == "succeeded":
        label, detail = "✅ Готово", "Результат доступен в истории и отправляется отдельным сообщением."
    elif generation.status == "failed":
        label, detail = "❌ Не удалось выполнить задачу", "Подробности — в уведомлении о результате и в истории."
    elif not active:
        label, detail = "⏹ Задача завершена", "Актуальный результат доступен в истории."
    elif not settings.telegram_generation_progress_enabled:
        label, detail = "Статус задачи", "Автообновление отключено. Следите за результатом в истории."
    else:
        if params.get("_submission_uncertain") or params.get("_quality_pending"):
            stage = "Проверяем результат"
            detail = "Ответ задерживается. Повторно запускать эту задачу не нужно."
        else:
            stage = {
                "queued": "В очереди",
                "retry": "Ожидаем обработки",
                "submitting": "Отправляем задачу",
                "generating": "Генерируем",
            }[generation.status]
            detail = "Сообщение обновляется автоматически. Можно закрыть Mini App."
        interval = max(5, settings.telegram_generation_progress_interval_seconds)
        frame = _SPINNER[(elapsed // interval) % len(_SPINNER)]
        label = f"{frame} {stage}"
        detail = f"Прошло: {minutes:02d}:{seconds:02d}\n\n{detail}"
    return f"<b>{label}</b>\n{title}\n\n{identity}\n\n{detail}"


def progress_keyboard(generation_id: uuid.UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📋 Скопировать UUID",
            copy_text=CopyTextButton(text=str(generation_id)),
        ),
    ]])


async def deliver_generation_progress(
    bot: Bot,
    *,
    session: AsyncSession,
    notification: Notification,
    delivery: NotificationDelivery,
    chat_id: int,
) -> None:
    """One outbox tick; the caller holds the delivery lock and commits the result.

    Never write generation state here: provider callbacks may finish concurrently.
    An edit uses the durable anchor, including after a worker lease is recovered.
    """
    generation = (
        await session.get(Generation, notification.generation_id, populate_existing=True)
        if notification.generation_id else None
    )
    if generation is None or generation.user_id != notification.user_id:
        await NotificationDeliveryService.mark_terminal(
            session, delivery, status="failed", error="progress_generation_owner_mismatch",
        )
        return
    if not settings.telegram_generation_progress_enabled and not delivery.external_message_id:
        await NotificationDeliveryService.mark_terminal(
            session, delivery, status="suppressed", error="generation_progress_disabled",
        )
        return

    text = progress_text(generation)
    keyboard = progress_keyboard(generation.id)
    operation = "edit" if delivery.external_message_id else "send"
    if delivery.external_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(delivery.external_message_id),
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except TelegramBadRequest as exc:
            error_text = str(exc).lower()
            if "message is not modified" in error_text:
                pass
            elif "message to edit not found" in error_text or "message can't be edited" in error_text:
                # Do not replace a deleted status on every tick. Final media delivery
                # has its own outbox row and remains independent of this message.
                await NotificationDeliveryService.mark_terminal(
                    session, delivery, status="undeliverable", error="progress_message_uneditable",
                )
                return
            else:
                raise
    else:
        message = await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_notification=True,
        )
        delivery.external_message_id = str(message.message_id)

    active = generation.status in _ACTIVE_STATES and settings.telegram_generation_progress_enabled
    if active:
        await NotificationDeliveryService.defer_without_attempt(
            session, delivery, error="",
            retry_after_seconds=settings.telegram_generation_progress_interval_seconds,
        )
    else:
        await NotificationDeliveryService.mark_sent(
            session, delivery, external_message_id=delivery.external_message_id,
        )
    logger.info(
        "generation_progress_updated",
        extra={
            "generation_id": str(generation.id), "delivery_id": str(delivery.id),
            "generation_status": generation.status, "progress_operation": operation,
            "progress_terminal": not active,
        },
    )
