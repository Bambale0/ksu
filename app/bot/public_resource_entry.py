from __future__ import annotations

import logging
import uuid
from typing import Any
from urllib.parse import urlparse

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import app_launcher_menu
from app.services.feed import FeedNotFoundError, FeedService
from app.services.feed_links import FeedDeepLink
from app.services.trends import TrendService

logger = logging.getLogger(__name__)


def _media_type(card: dict[str, Any], url: str) -> str:
    media = card.get("media") or []
    content_type = str(media[0].get("content_type") or "") if media else ""
    declared = str(card.get("media_type") or card.get("gen_type") or "")
    suffix = urlparse(url).path.lower()
    if declared == "video" or content_type.startswith("video/") or suffix.endswith((".mp4", ".mov", ".webm")):
        return "video"
    if declared == "audio" or content_type.startswith("audio/") or suffix.endswith((".mp3", ".wav", ".m4a", ".aac", ".ogg")):
        return "audio"
    return "image"


async def send_public_resource_entry(
    message: Message,
    session: AsyncSession,
    *,
    viewer_user_id: uuid.UUID,
    link: FeedDeepLink | None,
    payload: str | None,
) -> bool:
    """Preview one public resource, without enabling the retired feed browser."""
    if link is None or link.action not in {"feed", "remix", "trend"}:
        return False

    card: dict[str, Any]
    try:
        if link.action == "trend" and link.trend_id is not None:
            card = await TrendService.get_public(session, trend_id=link.trend_id)
            caption = "\n\n".join(
                part for part in (
                    f"🔥 {card.get('title') or 'Тренд ROXY'}",
                    str(card.get("description") or ""),
                    "Откройте этот тренд в ROXY кнопкой ниже.",
                ) if part
            )[:1024]
            url = str(card.get("preview_url") or "")
            route = "home"
        elif link.generation_id is not None:
            try:
                card = await FeedService.get_feed_generation_card(
                    session, generation_id=link.generation_id, viewer_user_id=viewer_user_id,
                )
            except FeedNotFoundError:
                # A profile-only public post is shareable too; private/removed
                # resources are rejected by both domain service methods.
                card = await FeedService.get_profile_generation_card(
                    session, generation_id=link.generation_id, viewer_user_id=viewer_user_id,
                )
            author = card.get("author") or {}
            caption = (
                "✨ Работа в ROXY\n"
                f"Автор: {author.get('display_name') or author.get('username') or 'Автор ROXY'}\n\n"
                "Откройте именно эту работу в приложении кнопкой ниже."
            )[:1024]
            # A Telegram preview must not bypass the app's moderation blur.
            url = "" if card.get("feed_blurred") else str(card.get("result_url") or "")
            route = "create" if link.action == "remix" else "feed"
        else:
            return False
    except (FeedNotFoundError, LookupError):
        await message.answer(
            "Эта работа сейчас недоступна. Возможно, автор убрал её из публикаций.",
            reply_markup=app_launcher_menu(route="home"), parse_mode=None,
        )
        return True

    keyboard = app_launcher_menu(route=route, start_payload=payload)
    if url:
        media_type = _media_type(card, url)
        try:
            if media_type == "video":
                await message.answer_video(
                    url, caption=caption, reply_markup=keyboard,
                    supports_streaming=True, parse_mode=None,
                )
            elif media_type == "audio":
                await message.answer_audio(url, caption=caption, reply_markup=keyboard, parse_mode=None)
            else:
                await message.answer_photo(url, caption=caption, reply_markup=keyboard, parse_mode=None)
            return True
        except TelegramBadRequest as exc:
            if "chat not found" in str(exc).lower():
                raise
            # A rejected media request sent nothing. Preserve the exact-resource
            # button; do not retry transport/forbidden failures and risk duplicates.
            logger.info("public_resource_preview_media_rejected", extra={"resource_kind": link.action})
    await message.answer(caption, reply_markup=keyboard, parse_mode=None)
    return True
