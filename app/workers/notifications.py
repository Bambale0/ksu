from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal
from urllib.parse import urlencode

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models import Generation, Notification, User
from app.db.notification_models import NotificationDelivery
from app.db.profile_models import UserPreference
from app.db.session import SessionFactory
from app.services.model_catalog import ModelCatalog, UnknownModelError
from app.services.notifications import NotificationDeliveryService

logger = logging.getLogger(__name__)

_GENERATION_NOTIFICATION_KINDS = {"generation_succeeded", "generation_failed"}


def _notification_text(notification: Notification) -> str:
    title = notification.title.strip()
    body = notification.body.strip()
    if title and body:
        return f"{title}\n\n{body}"
    return title or body or "У вас новое уведомление."


def _money(value: Decimal | object) -> str:
    try:
        return f"{Decimal(value):.2f}".rstrip("0").rstrip(".")
    except Exception:  # noqa: BLE001 - notification rendering must never break delivery
        return str(value)


def _generation_result_urls(generation: Generation) -> list[str]:
    raw = (generation.parameters or {}).get("_result_urls")
    result_urls = [str(value).strip() for value in raw] if isinstance(raw, list) else []
    if generation.result_url:
        result_urls.insert(0, str(generation.result_url).strip())
    return list(dict.fromkeys(value for value in result_urls if value.startswith(("https://", "http://"))))


def _generation_model_title(generation: Generation) -> str:
    model_id = str((generation.parameters or {}).get("_model_id") or "").strip()
    if not model_id:
        return "ROXY"
    try:
        return ModelCatalog.get(model_id).title
    except (UnknownModelError, KeyError):
        return model_id


def _generation_media_type(generation: Generation) -> str:
    model_id = str((generation.parameters or {}).get("_model_id") or "").strip()
    if model_id:
        try:
            return ModelCatalog.get(model_id).media_type
        except (UnknownModelError, KeyError):
            pass
    if generation.kind in {"image", "video", "audio"}:
        return generation.kind
    url = generation.result_url or ""
    path = url.split("?", 1)[0].lower()
    if path.endswith((".mp4", ".mov", ".webm")):
        return "video"
    if path.endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
        return "audio"
    return "image"


def _media_count_label(media_type: str, count: int) -> str:
    if media_type == "video":
        return f"{count} видео"
    if media_type == "audio":
        return f"{count} аудио"
    return f"{count} фото"


def _mini_app_url(generation_id: uuid.UUID) -> str | None:
    if not settings.public_base_url:
        return None
    query = urlencode({"route": "history", "generation": str(generation_id)})
    return f"{settings.public_base_url.rstrip('/')}/mini-app/?{query}"


def _generation_keyboard(generation: Generation, result_url: str | None = None) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    if result_url and result_url.startswith(("https://", "http://")):
        rows.append([InlineKeyboardButton(text="📥 Скачать оригинал", url=result_url)])
    app_url = _mini_app_url(generation.id)
    if app_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚀 Открыть в ROXY",
                    web_app=WebAppInfo(url=app_url),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def _generation_success_text(generation: Generation, *, result_count: int) -> str:
    media_type = _generation_media_type(generation)
    return (
        "✅ Генерация завершена\n\n"
        f"{_generation_model_title(generation)} · "
        f"{_media_count_label(media_type, result_count)} · {_money(generation.cost_rox)} ROX\n\n"
        "Результат готов 👇"
    )


def _generation_failure_text(generation: Generation) -> str:
    refund = ""
    try:
        if Decimal(generation.cost_rox) > 0:
            refund = f"\nСписанные {_money(generation.cost_rox)} ROX возвращены на баланс."
    except Exception:  # noqa: BLE001 - copy fallback only
        pass
    return (
        "❌ Генерация не выполнена\n\n"
        f"{_generation_model_title(generation)}\n"
        "Задача завершилась с ошибкой. Попробуйте ещё раз или откройте историю для деталей."
        f"{refund}"
    )


async def _generation_for_notification(
    session: AsyncSession,
    notification: Notification,
) -> Generation | None:
    if notification.kind not in _GENERATION_NOTIFICATION_KINDS:
        return None
    # New generation notifications use Generation.id as Notification.id. Older
    # queued notifications used random UUIDs and deliberately fall back to the
    # generic text sender, so deployment is backwards-compatible.
    generation = await session.get(Generation, notification.id)
    if generation is None or generation.user_id != notification.user_id:
        return None
    return generation


async def _send_generation_success(bot: Bot, *, chat_id: int, generation: Generation):  # type: ignore[no-untyped-def]
    urls = _generation_result_urls(generation)
    if not urls:
        return await bot.send_message(
            chat_id=chat_id,
            text=_generation_success_text(generation, result_count=1),
            reply_markup=_generation_keyboard(generation),
        )

    result_url = urls[0]
    text = _generation_success_text(generation, result_count=len(urls))
    keyboard = _generation_keyboard(generation, result_url)
    media_type = _generation_media_type(generation)

    try:
        if media_type == "video":
            return await bot.send_video(
                chat_id=chat_id,
                video=result_url,
                caption=text,
                reply_markup=keyboard,
                supports_streaming=True,
            )
        if media_type == "audio":
            return await bot.send_audio(
                chat_id=chat_id,
                audio=result_url,
                caption=text,
                reply_markup=keyboard,
            )
        return await bot.send_photo(
            chat_id=chat_id,
            photo=result_url,
            caption=text,
            reply_markup=keyboard,
        )
    except TelegramAPIError as exc:
        # Telegram may reject a valid generated asset as inline photo/video because
        # of media-specific limits or format sniffing. Preserve delivery by sending
        # the original as a document before falling back to the normal retry path.
        logger.info(
            "generation_notification_media_fallback",
            extra={"generation_id": str(generation.id), "media_type": media_type, "error": str(exc)},
        )
        return await bot.send_document(
            chat_id=chat_id,
            document=result_url,
            caption=text,
            reply_markup=keyboard,
        )


async def _send_generation_notification(
    bot: Bot,
    *,
    chat_id: int,
    notification: Notification,
    generation: Generation,
):  # type: ignore[no-untyped-def]
    if notification.kind == "generation_succeeded" and generation.status == "succeeded":
        return await _send_generation_success(bot, chat_id=chat_id, generation=generation)
    if notification.kind == "generation_failed" and generation.status == "failed":
        return await bot.send_message(
            chat_id=chat_id,
            text=_generation_failure_text(generation),
            reply_markup=_generation_keyboard(generation),
        )
    return await bot.send_message(chat_id=chat_id, text=_notification_text(notification))


async def _process_delivery(bot: Bot, delivery_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        delivery = await session.get(NotificationDelivery, delivery_id, with_for_update=True)
        if delivery is None or delivery.status != "sending":
            return
        notification = await session.get(Notification, delivery.notification_id)
        if notification is None:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="failed",
                error="notification_missing",
            )
            await session.commit()
            return
        user = await session.get(User, notification.user_id)
        if user is None or not user.is_active:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="undeliverable",
                error="user_inactive_or_missing",
            )
            await session.commit()
            return
        preference = await session.get(UserPreference, user.id)
        if preference is not None and not preference.notifications_enabled:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="suppressed",
                error="notifications_disabled",
            )
            await session.commit()
            return
        if (
            delivery.purpose == "marketing"
            and preference is not None
            and not preference.marketing_notifications
        ):
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="suppressed",
                error="marketing_notifications_disabled",
            )
            await session.commit()
            return

        try:
            generation = await _generation_for_notification(session, notification)
            if generation is not None:
                message = await _send_generation_notification(
                    bot,
                    chat_id=user.telegram_id,
                    notification=notification,
                    generation=generation,
                )
            else:
                message = await bot.send_message(
                    chat_id=user.telegram_id,
                    text=_notification_text(notification),
                )
        except TelegramForbiddenError as exc:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="undeliverable",
                error=f"telegram_forbidden:{exc}",
            )
        except TelegramRetryAfter as exc:
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"telegram_retry_after:{exc}",
                retry_after_seconds=int(exc.retry_after),
            )
        except TelegramAPIError as exc:
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"telegram_api:{exc}",
            )
        except Exception as exc:  # noqa: BLE001 - worker must persist retry state before continuing
            logger.exception("notification_delivery_unexpected_error", extra={"delivery_id": str(delivery.id)})
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"unexpected:{type(exc).__name__}:{exc}",
            )
        else:
            await NotificationDeliveryService.mark_sent(
                session,
                delivery,
                external_message_id=str(message.message_id),
            )
        await session.commit()


async def run() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is required for the notification worker")
    bot = Bot(settings.bot_token)
    try:
        while True:
            async with SessionFactory() as session:
                claimed = await NotificationDeliveryService.claim_batch(session)
                delivery_ids = [row.id for row in claimed]
                await session.commit()
            if not delivery_ids:
                await asyncio.sleep(settings.notification_worker_poll_seconds)
                continue
            for delivery_id in delivery_ids:
                await _process_delivery(bot, delivery_id)
    finally:
        await bot.session.close()


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
