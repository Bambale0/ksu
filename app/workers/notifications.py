from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal
from urllib.parse import urlencode

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models import Generation, Notification, User
from app.db.notification_models import NotificationDelivery
from app.db.profile_models import UserPreference
from app.db.session import SessionFactory
from app.services.generation_actions import GenerationActionService
from app.services.media_assets import MediaIngestService
from app.services.model_catalog import ModelCatalog, UnknownModelError
from app.services.notifications import NotificationDeliveryService

logger = logging.getLogger(__name__)

_GENERATION_NOTIFICATION_KINDS = {"generation_succeeded", "generation_failed"}
_TELEGRAM_MULTIPART_MAX_BYTES = 50 * 1024 * 1024


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


def _mini_app_url(
    generation_id: uuid.UUID,
    action: str | None = None,
    action_context_id: uuid.UUID | None = None,
) -> str | None:
    if not settings.public_base_url:
        return None
    base = f"{settings.public_base_url.rstrip('/')}/mini-app/"
    if action_context_id:
        return f"{base}?{urlencode({'route': 'generation-action', 'action_context_id': str(action_context_id)})}"
    query_data = {
        "route": "generation-action" if action else "history",
        "generation": str(generation_id),
    }
    if action:
        query_data["action"] = action
    query = urlencode(query_data)
    return f"{base}?{query}"


def _generation_keyboard(
    generation: Generation,
    original_url: str | None = None,
    action_context_ids: dict[str, uuid.UUID] | None = None,
) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []

    action_buttons: list[InlineKeyboardButton] = []
    for action in GenerationActionService.available_actions(generation):
        context_id = (action_context_ids or {}).get(action.id)
        action_url = _mini_app_url(generation.id, action.id, context_id)
        if not action_url:
            continue
        action_buttons.append(
            InlineKeyboardButton(
                text=action.label,
                web_app=WebAppInfo(url=action_url),
            )
        )
    for index in range(0, len(action_buttons), 2):
        rows.append(action_buttons[index:index + 2])

    utilities: list[InlineKeyboardButton] = []
    if original_url and original_url.startswith(("https://", "http://")):
        utilities.append(InlineKeyboardButton(text="📥 Скачать оригинал", url=original_url))
    app_url = _mini_app_url(generation.id)
    if app_url:
        utilities.append(
            InlineKeyboardButton(
                text="🚀 Открыть в ROXY",
                web_app=WebAppInfo(url=app_url),
            )
        )
    if utilities:
        rows.append(utilities)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _ensure_action_contexts(
    session: AsyncSession,
    generation: Generation,
) -> dict[str, uuid.UUID]:
    """Create server-owned action contexts for every delivered action button.

    Best-effort only: the durable notification path must never depend on the
    context store. If the snapshot build fails for any reason we skip the rows
    and keep the classic ``generation`` + ``action`` deep links, which the Mini
    App still resolves server-side on demand.
    """

    from app.services.generation_action_contexts import create_action_context

    if not settings.generation_action_contexts_enabled:
        return {}
    mapped: dict[str, uuid.UUID] = {}
    try:
        for action in GenerationActionService.available_actions(generation):
            context = await create_action_context(
                session,
                user_id=generation.user_id,
                generation=generation,
                action=action.id,
            )
            mapped[action.id] = context.id
    except Exception:  # noqa: BLE001 - delivery is the source of truth
        logger.info(
            "generation_action_contexts_creation_skipped",
            extra={"generation_id": str(generation.id)},
            exc_info=True,
        )
        return {}
    return mapped


def _generation_success_text(generation: Generation, *, result_count: int) -> str:
    media_type = _generation_media_type(generation)
    return (
        "✅ Генерация завершена\n\n"
        f"{_generation_model_title(generation)} · "
        f"{_media_count_label(media_type, result_count)} · {_money(generation.cost_rox)} ROX\n\n"
        "Результат готов 👇"
    )


def _friendly_generation_error(error: str | None) -> str:
    value = (error or "").strip().lower()
    if not value:
        return "Сервис генерации завершил задачу с ошибкой."
    if "timeout" in value or "timed out" in value:
        return "Сервис генерации не успел завершить задачу вовремя."
    if "rate" in value or "429" in value or "too many" in value:
        return "Сервис генерации временно перегружен."
    if "moder" in value or "safety" in value or "content" in value:
        return "Сервис генерации отклонил запрос по правилам контента."
    if "validation" in value or "invalid" in value or "required" in value:
        return "Провайдер отклонил параметры этой генерации."
    return "Сервис генерации завершил задачу с ошибкой."


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
        f"{_friendly_generation_error(generation.error)}"
        f"{refund}"
    )


async def _generation_for_notification(
    session: AsyncSession,
    notification: Notification,
) -> Generation | None:
    if notification.kind not in _GENERATION_NOTIFICATION_KINDS:
        return None
    generation = await session.get(Generation, notification.id)
    if generation is None or generation.user_id != notification.user_id:
        return None
    return generation


def _sync_generation_delivery(generation: Generation | None, delivery: NotificationDelivery) -> None:
    if generation is None:
        return
    generation.telegram_notification_status = delivery.status
    if delivery.status == "sent":
        generation.telegram_notification_sent_at = delivery.sent_at
        generation.telegram_message_id = delivery.external_message_id


async def _upload_video_from_server(
    bot: Bot,
    *,
    chat_id: int,
    generation: Generation,
    result_url: str,
    text: str,
    keyboard: InlineKeyboardMarkup | None,
):
    """Download the generated source and upload the local file to Telegram."""

    downloaded = None
    try:
        downloaded = await MediaIngestService._download(result_url)  # noqa: SLF001
        if downloaded.size_bytes > _TELEGRAM_MULTIPART_MAX_BYTES:
            logger.info(
                "generation_notification_video_too_large_for_telegram",
                extra={
                    "generation_id": str(generation.id),
                    "size_bytes": downloaded.size_bytes,
                },
            )
            return None

        suffix = downloaded.suffix if downloaded.suffix and downloaded.suffix != ".bin" else ".mp4"
        filename = f"roxy-{generation.id}{suffix}"
        try:
            return await bot.send_video(
                chat_id=chat_id,
                video=FSInputFile(downloaded.path, filename=filename),
                caption=text,
                reply_markup=keyboard,
                supports_streaming=True,
            )
        except TelegramAPIError as exc:
            logger.info(
                "generation_notification_video_document_fallback",
                extra={"generation_id": str(generation.id), "error": str(exc)},
            )
            return await bot.send_document(
                chat_id=chat_id,
                document=FSInputFile(downloaded.path, filename=filename),
                caption=text,
                reply_markup=keyboard,
            )
    except Exception as exc:  # noqa: BLE001 - URL/text fallback remains available
        logger.info(
            "generation_notification_video_upload_failed",
            extra={"generation_id": str(generation.id), "error": str(exc)},
        )
        return None
    finally:
        if downloaded is not None:
            downloaded.path.unlink(missing_ok=True)


async def _send_generation_success(  # type: ignore[no-untyped-def]
    bot: Bot,
    *,
    chat_id: int,
    generation: Generation,
    action_context_ids: dict[str, uuid.UUID] | None = None,
):
    urls = _generation_result_urls(generation)
    result_url = urls[0] if urls else None
    text = _generation_success_text(generation, result_count=max(1, len(urls)))
    keyboard = _generation_keyboard(generation, result_url, action_context_ids)
    if not result_url:
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)

    media_type = _generation_media_type(generation)

    if media_type == "video":
        # Video delivery is source-first: the worker downloads the provider result
        # and uploads the actual file to Telegram. This mirrors the expected photo
        # UX and avoids relying on Telegram being able to fetch a provider URL.
        uploaded = await _upload_video_from_server(
            bot,
            chat_id=chat_id,
            generation=generation,
            result_url=result_url,
            text=text,
            keyboard=keyboard,
        )
        if uploaded is not None:
            return uploaded

        # Keep a last-resort URL attempt only for cases where our downloader cannot
        # reach the provider or the file exceeds the cloud Bot API multipart limit.
        try:
            return await bot.send_video(
                chat_id=chat_id,
                video=result_url,
                caption=text,
                reply_markup=keyboard,
                supports_streaming=True,
            )
        except TelegramAPIError as exc:
            logger.info(
                "generation_notification_video_url_fallback_failed",
                extra={"generation_id": str(generation.id), "error": str(exc)},
            )
            return await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)

    try:
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
        logger.info(
            "generation_notification_media_url_failed",
            extra={"generation_id": str(generation.id), "media_type": media_type, "error": str(exc)},
        )
        return await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)


async def _send_generation_notification(  # type: ignore[no-untyped-def]
    bot: Bot,
    *,
    chat_id: int,
    notification: Notification,
    generation: Generation,
    action_context_ids: dict[str, uuid.UUID] | None = None,
):
    if notification.kind == "generation_succeeded" and generation.status == "succeeded":
        return await _send_generation_success(
            bot,
            chat_id=chat_id,
            generation=generation,
            action_context_ids=action_context_ids,
        )
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

        generation = await _generation_for_notification(session, notification)
        if generation is not None and (
            generation.telegram_notification_sent_at is not None
            or generation.telegram_notification_status == "sent"
        ):
            await NotificationDeliveryService.mark_sent(
                session,
                delivery,
                external_message_id=generation.telegram_message_id,
            )
            generation.telegram_notification_status = "sent"
            await session.commit()
            return

        if generation is not None:
            generation.telegram_notification_status = "sending"

        user = await session.get(User, notification.user_id)
        if user is None or not user.is_active:
            await NotificationDeliveryService.mark_terminal(
                session,
                delivery,
                status="undeliverable",
                error="user_inactive_or_missing",
            )
            _sync_generation_delivery(generation, delivery)
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
            _sync_generation_delivery(generation, delivery)
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
            _sync_generation_delivery(generation, delivery)
            await session.commit()
            return

        try:
            action_context_ids: dict[str, uuid.UUID] = {}
            if generation is not None:
                action_context_ids = await _ensure_action_contexts(session, generation)
            if generation is not None:
                message = await _send_generation_notification(
                    bot,
                    chat_id=user.telegram_id,
                    notification=notification,
                    generation=generation,
                    action_context_ids=action_context_ids,
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
            _sync_generation_delivery(generation, delivery)
        except TelegramRetryAfter as exc:
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"telegram_retry_after:{exc}",
                retry_after_seconds=int(exc.retry_after),
            )
            _sync_generation_delivery(generation, delivery)
        except TelegramAPIError as exc:
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"telegram_api:{exc}",
            )
            _sync_generation_delivery(generation, delivery)
        except Exception as exc:  # noqa: BLE001 - worker must persist retry state before continuing
            logger.exception("notification_delivery_unexpected_error", extra={"delivery_id": str(delivery.id)})
            await NotificationDeliveryService.mark_retry(
                session,
                delivery,
                error=f"unexpected:{type(exc).__name__}:{exc}",
            )
            _sync_generation_delivery(generation, delivery)
        else:
            await NotificationDeliveryService.mark_sent(
                session,
                delivery,
                external_message_id=str(message.message_id),
            )
            _sync_generation_delivery(generation, delivery)
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
