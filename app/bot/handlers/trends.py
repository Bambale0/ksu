from __future__ import annotations

from urllib.parse import urlencode

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    WebAppInfo,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import BACK_TEXT, back_menu
from app.core.config import settings
from app.services.trends import TrendService
from app.services.users import UserService

router = Router(name="trends")


def _runner_url(trend_id: str) -> str:
    base = f"{settings.public_base_url.rstrip('/')}/mini-app/trends.html"
    return f"{base}?{urlencode({'trend': trend_id})}"


def _caption(card: dict[str, object]) -> str:
    model = card.get("model") or {}
    model_title = model.get("title") if isinstance(model, dict) else "AI"
    refs = card.get("reference_requirements") or {}
    min_refs = int(refs.get("min", 0)) if isinstance(refs, dict) else 0
    lines = [
        f"🔥 {card.get('title')}",
        str(card.get("description") or ""),
        "",
        f"✨ {model_title}",
        f"💎 {card.get('cost_credits')} кр. · ≈ {card.get('cost_rub')} ₽",
    ]
    if min_refs:
        lines.append(f"🖼 Нужно примеров: от {min_refs}")
    if card.get("media_type") == "video" and card.get("billing_seconds"):
        lines.append(f"⏱ {card.get('billing_seconds')} сек.")
    lines.extend(["", "🔒 Описание и настройки скрыты"])
    return "\n".join(line for line in lines if line is not None)[:1024]


def _keyboard(card: dict[str, object], index: int, total: int) -> InlineKeyboardMarkup:
    trend_id = str(card["id"])
    rows: list[list[InlineKeyboardButton]] = []
    if total > 1:
        rows.append(
            [
                InlineKeyboardButton(text="◀️", callback_data=f"tr:n:{(index - 1) % total}"),
                InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="tr:noop"),
                InlineKeyboardButton(text="▶️", callback_data=f"tr:n:{(index + 1) % total}"),
            ]
        )
    if settings.public_base_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "🔥 Повторить видео"
                        if card.get("media_type") == "video"
                        else "🔥 Повторить шаблон"
                    ),
                    web_app=WebAppInfo(url=_runner_url(trend_id)),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=BACK_TEXT, callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _cards(session: AsyncSession) -> list[dict[str, object]]:
    payload = await TrendService.list_public(session, limit=100)
    return list(payload.get("items") or [])


async def _send_card(message: Message, card: dict[str, object], index: int, total: int) -> None:
    preview_url = str(card.get("preview_url") or "")
    if card.get("media_type") == "video":
        await message.answer_video(
            preview_url,
            caption=_caption(card),
            reply_markup=_keyboard(card, index, total),
            supports_streaming=True,
        )
    else:
        await message.answer_photo(
            preview_url,
            caption=_caption(card),
            reply_markup=_keyboard(card, index, total),
        )


async def _edit_card(
    callback: CallbackQuery,
    card: dict[str, object],
    index: int,
    total: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    preview_url = str(card.get("preview_url") or "")
    media = (
        InputMediaVideo(media=preview_url, caption=_caption(card), supports_streaming=True)
        if card.get("media_type") == "video"
        else InputMediaPhoto(media=preview_url, caption=_caption(card))
    )
    try:
        await callback.message.edit_media(
            media=media,
            reply_markup=_keyboard(card, index, total),
        )
    except TelegramBadRequest:
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await _send_card(callback.message, card, index, total)
    await callback.answer()


async def _open(message: Message, session: AsyncSession) -> None:
    await UserService.get_or_create(session, message.from_user)
    cards = await _cards(session)
    if not cards:
        await message.answer("🔥 Тренды пока не опубликованы.", reply_markup=back_menu())
        return
    await _send_card(message, cards[0], 0, len(cards))


@router.message(Command("trends"))
@router.message(Command("prompts"))
async def trends_command(message: Message, session: AsyncSession) -> None:
    await _open(message, session)


@router.callback_query(F.data == "trends:open")
async def trends_open(callback: CallbackQuery, session: AsyncSession) -> None:
    await UserService.get_or_create(session, callback.from_user)
    cards = await _cards(session)
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    if not cards:
        await callback.message.answer("🔥 Тренды пока не опубликованы.", reply_markup=back_menu())
        return
    await _send_card(callback.message, cards[0], 0, len(cards))


@router.callback_query(F.data.startswith("tr:n:"))
async def trends_navigate(callback: CallbackQuery, session: AsyncSession) -> None:
    cards = await _cards(session)
    if not cards:
        await callback.answer("Тренды недоступны", show_alert=True)
        return
    try:
        index = int((callback.data or "").split(":", 2)[-1]) % len(cards)
    except ValueError:
        index = 0
    await _edit_card(callback, cards[index], index, len(cards))


@router.callback_query(F.data == "tr:noop")
async def trends_noop(callback: CallbackQuery) -> None:
    await callback.answer()
