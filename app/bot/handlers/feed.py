from __future__ import annotations

import uuid
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feed import FeedError, FeedNotFoundError, FeedService
from app.services.feed_links import FeedDeepLink
from app.services.users import UserService
from app.services.wallet import InsufficientBalanceError

router = Router(name="feed")

_SORT_CODES = {"r": "recent", "d": "top_day", "t": "top"}


class FeedCommentFlow(StatesGroup):
    waiting_text = State()


def _surface_for_context(context: str) -> str:
    if context.startswith("p:") or context == "x:p":
        return "profile"
    return "feed"


def _context_index(context: str) -> int | None:
    parts = context.split(":")
    if parts[0] == "g" and len(parts) == 3:
        try:
            return int(parts[2])
        except ValueError:
            return None
    if parts[0] == "p" and len(parts) == 3:
        try:
            return int(parts[2])
        except ValueError:
            return None
    return None


def _context_with_index(context: str, index: int) -> str:
    parts = context.split(":")
    if parts[0] == "g" and len(parts) == 3:
        return f"g:{parts[1]}:{index}"
    if parts[0] == "p" and len(parts) == 3:
        return f"p:{parts[1]}:{index}"
    return context


def _is_video(card: dict[str, Any]) -> bool:
    media = card.get("media") or []
    if media and str(media[0].get("content_type") or "").startswith("video/"):
        return True
    url = str(card.get("result_url") or "").lower().split("?", 1)[0]
    return url.endswith((".mp4", ".webm", ".mov"))


def _caption(card: dict[str, Any], comments: list[dict[str, Any]] | None = None) -> str:
    author = card.get("author") or {}
    display = str(author.get("display_name") or "Автор")
    username = str(author.get("username") or "")
    author_line = f"{display} · @{username}" if username else display
    lines = [
        f"👤 {author_line}",
        f"✨ {card.get('model') or card.get('gen_type') or 'AI'}",
    ]
    prompt = str(card.get("prompt") or "")
    if prompt:
        trimmed = prompt if len(prompt) <= 460 else prompt[:457] + "…"
        lines.extend(["", trimmed])
    elif card.get("prompt_hidden"):
        lines.extend(["", "🔒 Prompt скрыт"])
    lines.extend(
        [
            "",
            f"❤️ {card.get('likes_count', 0)}   🔗 {card.get('shares_count', 0)}   💬 {card.get('comments_count', 0)}   🔁 {card.get('remixes', 0)}",
        ]
    )
    if card.get("publication_scope") == "profile":
        lines.append("👤 Публикация только в профиле")
    if card.get("feed_blurred"):
        lines.append("⚠️ Контент скрыт блюром")
    if comments is not None:
        lines.extend(["", "💬 Комментарии:"])
        if not comments:
            lines.append("Пока нет комментариев")
        for item in comments[:4]:
            author_info = item.get("author") or {}
            name = str(
                author_info.get("display_name")
                or author_info.get("username")
                or "Пользователь"
            )
            text = str(item.get("text") or "")
            if len(text) > 120:
                text = text[:117] + "…"
            lines.append(f"• {name}: {text}")
    return "\n".join(lines)[:1024]


def _keyboard(
    card: dict[str, Any],
    context: str,
    total: int | None = None,
) -> InlineKeyboardMarkup:
    generation_id = str(card["id"])
    rows: list[list[InlineKeyboardButton]] = []
    index = _context_index(context)
    if index is not None and total:
        prev_index = (index - 1) % total
        next_index = (index + 1) % total
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"fd:n:{_context_with_index(context, prev_index)}",
                ),
                InlineKeyboardButton(
                    text=f"{index + 1}/{total}",
                    callback_data="fd:noop",
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"fd:n:{_context_with_index(context, next_index)}",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=f"{'❤️' if card.get('liked_by_me') else '♡'} {card.get('likes_count', 0)}",
                callback_data=f"fd:l:{context}:{generation_id}",
            ),
            InlineKeyboardButton(
                text="🔗 Ссылка",
                callback_data=f"fd:s:{context}:{generation_id}",
            ),
            InlineKeyboardButton(
                text="🔁 Повторить",
                callback_data=f"fd:r:{context}:{generation_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="👤 Автор",
                callback_data=f"fd:a:{card.get('author_referral_code')}",
            ),
            InlineKeyboardButton(
                text="💬 Комментарии",
                callback_data=f"fd:c:{context}:{generation_id}",
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="🆕 Новые", callback_data="fd:n:g:r:0"),
            InlineKeyboardButton(text="🔥 Топ дня", callback_data="fd:n:g:d:0"),
            InlineKeyboardButton(text="⭐ Топ", callback_data="fd:n:g:t:0"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav:main")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _comments_keyboard(card: dict[str, Any], context: str) -> InlineKeyboardMarkup:
    generation_id = str(card["id"])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✍️ Написать комментарий",
                    callback_data=f"fd:w:{context}:{generation_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К посту",
                    callback_data=f"fd:b:{context}:{generation_id}",
                )
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav:main")],
        ]
    )


async def _load_context(
    session: AsyncSession,
    *,
    viewer_user_id: uuid.UUID,
    context: str,
) -> tuple[list[dict[str, Any]], int]:
    parts = context.split(":")
    if parts[0] == "g" and len(parts) == 3:
        sort = _SORT_CODES.get(parts[1], "recent")
        try:
            index = max(0, int(parts[2]))
        except ValueError:
            index = 0
        rows = await FeedService.get_feed_generations(
            session,
            sort=sort,
            limit=50,
            offset=0,
        )
        cards = await FeedService.cards_for_generations(
            session,
            rows,
            viewer_user_id=viewer_user_id,
            surface="feed",
        )
        return cards, index
    if parts[0] == "p" and len(parts) == 3:
        author = await FeedService.author_by_referral_code(session, parts[1])
        try:
            index = max(0, int(parts[2]))
        except ValueError:
            index = 0
        rows = await FeedService.get_user_feed_generations(
            session,
            author_user_id=author.id,
            profile_visible_only=True,
            limit=50,
            offset=0,
        )
        cards = await FeedService.cards_for_generations(
            session,
            rows,
            viewer_user_id=viewer_user_id,
            surface="profile",
        )
        return cards, index
    raise FeedNotFoundError("Feed context not found")


async def _card_by_id(
    session: AsyncSession,
    *,
    viewer_user_id: uuid.UUID,
    generation_id: uuid.UUID,
    surface: str,
) -> dict[str, Any]:
    if surface == "profile":
        return await FeedService.get_profile_generation_card(
            session,
            generation_id=generation_id,
            viewer_user_id=viewer_user_id,
        )
    return await FeedService.get_feed_generation_card(
        session,
        generation_id=generation_id,
        viewer_user_id=viewer_user_id,
    )


async def _send_card(
    message: Message,
    card: dict[str, Any],
    context: str,
    total: int | None = None,
) -> None:
    url = str(card.get("result_url") or "")
    if not url:
        await message.answer("Медиа публикации недоступно.")
        return
    caption = _caption(card)
    keyboard = _keyboard(card, context, total)
    if _is_video(card):
        await message.answer_video(
            url,
            caption=caption,
            reply_markup=keyboard,
            supports_streaming=True,
        )
    else:
        await message.answer_photo(url, caption=caption, reply_markup=keyboard)


async def _edit_card(
    callback: CallbackQuery,
    card: dict[str, Any],
    context: str,
    total: int | None = None,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    url = str(card.get("result_url") or "")
    if not url:
        await callback.answer("Медиа недоступно", show_alert=True)
        return
    caption = _caption(card)
    media = (
        InputMediaVideo(media=url, caption=caption, supports_streaming=True)
        if _is_video(card)
        else InputMediaPhoto(media=url, caption=caption)
    )
    try:
        await callback.message.edit_media(
            media=media,
            reply_markup=_keyboard(card, context, total),
        )
    except TelegramBadRequest:
        # Telegram cannot always swap media kinds. Replace the single active carousel message.
        try:
            await callback.message.delete()
        except TelegramBadRequest:
            pass
        await _send_card(callback.message, card, context, total)
    await callback.answer()


async def _open_context(
    callback: CallbackQuery,
    session: AsyncSession,
    context: str,
) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    try:
        cards, index = await _load_context(
            session,
            viewer_user_id=user.id,
            context=context,
        )
    except FeedNotFoundError:
        await callback.answer("Лента недоступна", show_alert=True)
        return
    if not cards:
        await callback.answer(
            "В профиле пока нет публикаций"
            if context.startswith("p:")
            else "В ленте пока пусто",
            show_alert=True,
        )
        return
    index %= len(cards)
    await _edit_card(
        callback,
        cards[index],
        _context_with_index(context, index),
        len(cards),
    )


@router.callback_query(F.data == "feed:open")
async def feed_open(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    rows = await FeedService.get_feed_generations(
        session,
        sort="recent",
        limit=50,
        offset=0,
    )
    cards = await FeedService.cards_for_generations(
        session,
        rows,
        viewer_user_id=user.id,
        surface="feed",
    )
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    if not cards:
        await callback.message.answer("🌐 В публичной ленте пока нет работ.")
        return
    await _send_card(callback.message, cards[0], "g:r:0", len(cards))


@router.callback_query(F.data.startswith("fd:n:"))
async def feed_navigate(callback: CallbackQuery, session: AsyncSession) -> None:
    context = (callback.data or "")[5:]
    await _open_context(callback, session, context)


@router.callback_query(F.data == "fd:noop")
async def feed_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("fd:a:"))
async def feed_author(callback: CallbackQuery, session: AsyncSession) -> None:
    code = (callback.data or "").split(":", 2)[-1]
    await _open_context(callback, session, f"p:{code}:0")


@router.callback_query(F.data.startswith("fd:l:"))
async def feed_like(callback: CallbackQuery, session: AsyncSession) -> None:
    data = callback.data or ""
    raw = data[5:]
    context, generation_raw = raw.rsplit(":", 1)
    try:
        generation_id = uuid.UUID(generation_raw)
    except ValueError:
        await callback.answer("Некорректный пост", show_alert=True)
        return
    user = await UserService.get_or_create(session, callback.from_user)
    surface = _surface_for_context(context)
    try:
        card = await _card_by_id(
            session,
            viewer_user_id=user.id,
            generation_id=generation_id,
            surface=surface,
        )
        if card.get("liked_by_me"):
            await FeedService.unlike_feed_generation(
                session,
                generation_id=generation_id,
                user_id=user.id,
                surface=surface,
            )
        else:
            await FeedService.like_feed_generation(
                session,
                generation_id=generation_id,
                user_id=user.id,
                surface=surface,
            )
        await session.commit()
        card = await _card_by_id(
            session,
            viewer_user_id=user.id,
            generation_id=generation_id,
            surface=surface,
        )
    except (FeedError, FeedNotFoundError):
        await callback.answer("Публикация больше недоступна", show_alert=True)
        return
    total = None
    if _context_index(context) is not None:
        cards, _ = await _load_context(
            session,
            viewer_user_id=user.id,
            context=context,
        )
        total = len(cards)
    await _edit_card(callback, card, context, total)


@router.callback_query(F.data.startswith("fd:s:"))
async def feed_share(callback: CallbackQuery, session: AsyncSession) -> None:
    raw = (callback.data or "")[5:]
    context, generation_raw = raw.rsplit(":", 1)
    try:
        generation_id = uuid.UUID(generation_raw)
    except ValueError:
        await callback.answer("Некорректный пост", show_alert=True)
        return
    user = await UserService.get_or_create(session, callback.from_user)
    surface = _surface_for_context(context)
    try:
        card = await _card_by_id(
            session,
            viewer_user_id=user.id,
            generation_id=generation_id,
            surface=surface,
        )
        count = await FeedService.increment_feed_share(
            session,
            generation_id=generation_id,
            surface=surface,
        )
        await session.commit()
        link = FeedService.post_deep_link(
            generation_id,
            str(card["author_referral_code"]),
        )
    except (FeedError, FeedNotFoundError):
        await callback.answer("Публикация больше недоступна", show_alert=True)
        return
    await callback.answer(f"Share #{count}")
    if isinstance(callback.message, Message) and link:
        await callback.message.answer(f"🔗 {link}")


@router.callback_query(F.data.startswith("fd:r:"))
async def feed_remix(
    callback: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
) -> None:
    raw = (callback.data or "")[5:]
    context, generation_raw = raw.rsplit(":", 1)
    try:
        generation_id = uuid.UUID(generation_raw)
    except ValueError:
        await callback.answer("Некорректный пост", show_alert=True)
        return
    user = await UserService.get_or_create(session, callback.from_user)
    try:
        generation = await FeedService.remix(
            session,
            redis,
            source_generation_id=generation_id,
            remix_author_id=user.id,
            surface=_surface_for_context(context),
        )
    except InsufficientBalanceError:
        await callback.answer("Недостаточно кредитов", show_alert=True)
        return
    except (FeedError, FeedNotFoundError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer("Remix запущен")
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"⏳ Повтор запущен: {generation.id}\n"
            "Prompt исходной работы не передавался клиенту."
        )


@router.callback_query(F.data.startswith("fd:c:"))
async def feed_comments(callback: CallbackQuery, session: AsyncSession) -> None:
    raw = (callback.data or "")[5:]
    context, generation_raw = raw.rsplit(":", 1)
    try:
        generation_id = uuid.UUID(generation_raw)
    except ValueError:
        await callback.answer("Некорректный пост", show_alert=True)
        return
    user = await UserService.get_or_create(session, callback.from_user)
    surface = _surface_for_context(context)
    try:
        card = await _card_by_id(
            session,
            viewer_user_id=user.id,
            generation_id=generation_id,
            surface=surface,
        )
        comments = await FeedService.get_feed_comments(
            session,
            generation_id=generation_id,
            surface=surface,
            limit=10,
        )
    except (FeedError, FeedNotFoundError):
        await callback.answer("Комментарии недоступны", show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_caption(
            caption=_caption(card, comments),
            reply_markup=_comments_keyboard(card, context),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("fd:b:"))
async def feed_back_to_post(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    raw = (callback.data or "")[5:]
    context, generation_raw = raw.rsplit(":", 1)
    try:
        generation_id = uuid.UUID(generation_raw)
    except ValueError:
        await callback.answer("Некорректный пост", show_alert=True)
        return
    user = await UserService.get_or_create(session, callback.from_user)
    surface = _surface_for_context(context)
    try:
        card = await _card_by_id(
            session,
            viewer_user_id=user.id,
            generation_id=generation_id,
            surface=surface,
        )
    except (FeedError, FeedNotFoundError):
        await callback.answer("Публикация недоступна", show_alert=True)
        return
    total = None
    if _context_index(context) is not None:
        cards, _ = await _load_context(
            session,
            viewer_user_id=user.id,
            context=context,
        )
        total = len(cards)
    if isinstance(callback.message, Message):
        await callback.message.edit_caption(
            caption=_caption(card),
            reply_markup=_keyboard(card, context, total),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("fd:w:"))
async def feed_comment_start(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    raw = (callback.data or "")[5:]
    context, generation_raw = raw.rsplit(":", 1)
    try:
        generation_id = uuid.UUID(generation_raw)
    except ValueError:
        await callback.answer("Некорректный пост", show_alert=True)
        return
    surface = _surface_for_context(context)
    try:
        await FeedService.assert_surface_visible(
            session,
            generation_id,
            surface=surface,
        )
    except FeedNotFoundError:
        await callback.answer("Публикация недоступна", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    await state.set_state(FeedCommentFlow.waiting_text)
    await state.update_data(
        feed_generation_id=str(generation_id),
        feed_surface=surface,
        feed_context=context,
        feed_chat_id=callback.message.chat.id,
        feed_message_id=callback.message.message_id,
    )
    await callback.answer("Отправьте комментарий")


@router.message(FeedCommentFlow.waiting_text)
async def feed_comment_submit(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.from_user is None or not message.text:
        return
    data = await state.get_data()
    try:
        generation_id = uuid.UUID(str(data["feed_generation_id"]))
        surface = str(data["feed_surface"])
        context = str(data["feed_context"])
        chat_id = int(data["feed_chat_id"])
        message_id = int(data["feed_message_id"])
    except (KeyError, ValueError, TypeError):
        await state.clear()
        return
    user = await UserService.get_or_create(session, message.from_user)
    try:
        await FeedService.add_feed_comment(
            session,
            generation_id=generation_id,
            user_id=user.id,
            surface=surface,
            text=message.text,
        )
        await session.commit()
        card = await _card_by_id(
            session,
            viewer_user_id=user.id,
            generation_id=generation_id,
            surface=surface,
        )
        comments = await FeedService.get_feed_comments(
            session,
            generation_id=generation_id,
            surface=surface,
            limit=10,
        )
        await message.bot.edit_message_caption(
            chat_id=chat_id,
            message_id=message_id,
            caption=_caption(card, comments),
            reply_markup=_comments_keyboard(card, context),
        )
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
    except (FeedError, FeedNotFoundError) as exc:
        await message.answer(f"Комментарий не добавлен: {exc}")
    finally:
        await state.clear()


async def handle_deep_link(
    message: Message,
    *,
    user_id: uuid.UUID,
    link: FeedDeepLink,
    session: AsyncSession,
    redis: Redis,
) -> bool:
    if link.action == "ref":
        return False
    if link.action == "posts" and link.profile_referral_code:
        try:
            author = await FeedService.author_by_referral_code(
                session,
                link.profile_referral_code,
            )
            rows = await FeedService.get_user_feed_generations(
                session,
                author_user_id=author.id,
                profile_visible_only=True,
                limit=50,
                offset=0,
            )
            cards = await FeedService.cards_for_generations(
                session,
                rows,
                viewer_user_id=user_id,
                surface="profile",
            )
        except FeedNotFoundError:
            await message.answer("Профиль не найден.")
            return True
        if not cards:
            await message.answer("В профиле автора пока нет публикаций.")
            return True
        await _send_card(
            message,
            cards[0],
            f"p:{link.profile_referral_code}:0",
            len(cards),
        )
        return True

    if link.generation_id is None:
        return False

    if link.action == "feed":
        card: dict[str, Any] | None = None
        context = "x:f"
        try:
            card = await FeedService.get_feed_generation_card(
                session,
                generation_id=link.generation_id,
                viewer_user_id=user_id,
            )
        except FeedNotFoundError:
            try:
                card = await FeedService.get_profile_generation_card(
                    session,
                    generation_id=link.generation_id,
                    viewer_user_id=user_id,
                )
                context = "x:p"
            except FeedNotFoundError:
                pass
        if card is None:
            await message.answer("Публикация удалена или недоступна.")
            return True
        await _send_card(message, card, context)
        return True

    if link.action == "remix":
        surface = "feed"
        try:
            await FeedService.assert_surface_visible(
                session,
                link.generation_id,
                surface="feed",
            )
        except FeedNotFoundError:
            try:
                await FeedService.assert_surface_visible(
                    session,
                    link.generation_id,
                    surface="profile",
                )
                surface = "profile"
            except FeedNotFoundError:
                await message.answer("Исходная публикация удалена или недоступна.")
                return True
        try:
            generation = await FeedService.remix(
                session,
                redis,
                source_generation_id=link.generation_id,
                remix_author_id=user_id,
                surface=surface,
            )
        except InsufficientBalanceError:
            await message.answer("Недостаточно кредитов для повтора.")
            return True
        except FeedError as exc:
            await message.answer(f"Повтор не запущен: {exc}")
            return True
        await message.answer(
            f"⏳ Remix запущен: {generation.id}\n"
            "Исходный prompt восстановлен сервером и не передавался в deep link."
        )
        return True
    return False
