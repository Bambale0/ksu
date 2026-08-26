from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    QUICK_MENU_TEXT,
    QUICK_PROMPT_TEXT,
    QUICK_SUPPORT_TEXT,
    QUICK_VIDEO_PROMPT_TEXT,
    app_launcher_menu,
    prompt_tools_menu,
    quick_menu,
)
from app.bot.support_links import direct_support_handle
from app.core.config import settings
from app.db.models import User
from app.services.feed import FeedNotFoundError, FeedService
from app.services.feed_links import FeedDeepLink, parse_feed_deep_link, start_payload
from app.services.users import UserService

router = Router(name="app_launcher")


def _start_link(text: str | None) -> FeedDeepLink | None:
    return parse_feed_deep_link(start_payload(text))


def _launcher_route(link: FeedDeepLink | None) -> str:
    if link is None or link.action == "ref":
        return "catalog"
    if link.action == "feed":
        return "feed"
    if link.action == "posts":
        return "profile"
    if link.action == "remix":
        return "create"
    return "catalog"


async def _validated_inviter(session: AsyncSession, link: FeedDeepLink | None) -> int | None:
    if link is None:
        return None
    if link.action == "ref":
        return link.referral_telegram_id
    if link.action == "posts" and link.profile_referral_code:
        if str(link.referral_telegram_id) != link.profile_referral_code:
            return None
        try:
            author = await FeedService.author_by_referral_code(session, link.profile_referral_code)
        except FeedNotFoundError:
            return None
        return author.telegram_id
    if link.generation_id is None:
        return None

    generation = None
    for surface in ("feed", "profile"):
        try:
            generation = await FeedService.assert_surface_visible(
                session,
                link.generation_id,
                surface=surface,
            )
            break
        except FeedNotFoundError:
            continue
    if generation is None:
        return None
    author = await session.get(User, generation.user_id)
    if author is None or author.telegram_id != link.referral_telegram_id:
        return None
    return author.telegram_id


def _support_handle() -> str | None:
    return direct_support_handle(settings.support_telegram_url)


def _support_line() -> str:
    handle = _support_handle()
    if handle:
        return f"Поддержка: {handle}"
    return "Поддержка: кнопка снизу или раздел «Профиль → Поддержка» в ROXY"


async def _send_launcher(message: Message, *, route: str, payload: str | None) -> None:
    await message.answer(
        "Меню и поддержка закреплены снизу.",
        reply_markup=quick_menu(),
    )
    await message.answer(
        "<b>Добро пожаловать в ROXY ✨</b>\n\n"
        "Создавайте изображения, видео и музыку.\n"
        "А ещё ROXY помогает собрать подробное описание по фото, видео или идее.\n"
        "Если не знаете, как красиво описать идею — откройте приложение, загрузите фото, видео "
        "или напишите задумку, а ROXY подготовит текст для запуска.\n\n"
        "<b>Бонусы:</b>\n"
        "🎁 50 ROX — сразу после регистрации\n"
        "🎁 +30 ROX — за друга после его первой генерации\n\n"
        "Нажмите <b>«🚀 Открыть ROXY»</b>, чтобы перейти в приложение.\n"
        f"{_support_line()}",
        reply_markup=app_launcher_menu(route=route, start_payload=payload),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "app:unavailable")
async def app_unavailable(callback: CallbackQuery) -> None:
    await callback.answer(
        "ROXY временно недоступна. Попробуйте открыть приложение чуть позже.",
        show_alert=True,
    )


@router.message(CommandStart())
async def start_app_only(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        return
    await state.clear()
    link = _start_link(message.text)
    await UserService.get_or_create(
        session,
        message.from_user,
        inviter_telegram_id=await _validated_inviter(session, link),
    )
    await session.commit()
    await _send_launcher(
        message,
        route=_launcher_route(link),
        payload=start_payload(message.text),
    )


@router.message(F.text == QUICK_MENU_TEXT)
async def menu_shortcut(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await state.clear()
    await UserService.get_or_create(session, message.from_user)
    await session.commit()
    await _send_launcher(message, route="catalog", payload=None)


@router.message(F.text == QUICK_SUPPORT_TEXT)
async def support_shortcut(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await state.clear()
    await UserService.get_or_create(session, message.from_user)
    await session.commit()

    handle = _support_handle()
    if handle:
        await message.answer(
            "Поддержка ROXY всегда рядом.\n\n"
            f"Напишите {handle} — поможем с оплатой, балансом, созданием работ, описаниями и публикациями.",
            reply_markup=quick_menu(),
        )
        return

    await message.answer(
        "Поддержка ROXY всегда рядом.\n\n"
        "Откройте ROXY → Профиль → Поддержка и создайте обращение. "
        "Так заявка сохранится в системе, а ответ придёт в уведомления.",
        reply_markup=app_launcher_menu(route="profile"),
    )


@router.message(F.text.in_({QUICK_PROMPT_TEXT, QUICK_VIDEO_PROMPT_TEXT}))
async def retired_prompt_shortcut(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """Clean up old bottom prompt buttons while preserving a path to the tools."""
    if message.from_user is None:
        return
    await state.clear()
    await UserService.get_or_create(session, message.from_user)
    await session.commit()
    await message.answer("Меню обновлено: снизу только меню и поддержка.", reply_markup=quick_menu())
    await message.answer(
        "Инструменты для описаний открываются внутри ROXY или кнопками ниже.",
        reply_markup=prompt_tools_menu(),
    )


@router.message()
async def redirect_everything_to_app(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    """Do not expose a parallel text UI: any customer message returns the app launcher."""
    if message.from_user is None:
        return
    await state.clear()
    await UserService.get_or_create(session, message.from_user)
    await session.commit()
    await _send_launcher(message, route="catalog", payload=None)
