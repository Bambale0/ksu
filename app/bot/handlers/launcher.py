from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import QUICK_SUPPORT_TEXT, SUPPORT_USERNAME, app_launcher_menu
from app.db.models import User
from app.services.feed import FeedNotFoundError, FeedService
from app.services.feed_links import FeedDeepLink, parse_feed_deep_link, start_payload
from app.services.users import UserService

router = Router(name="app_launcher")


def _start_link(text: str | None) -> FeedDeepLink | None:
    return parse_feed_deep_link(start_payload(text))


def _launcher_route(link: FeedDeepLink | None) -> str:
    if link is None or link.action == "ref":
        return "home"
    if link.action == "feed":
        return "feed"
    if link.action == "posts":
        return "profile"
    if link.action == "remix":
        return "create"
    return "home"


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


async def _send_launcher(message: Message, *, route: str, payload: str | None) -> None:
    await message.answer("Открываю ROXY ✨", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "<b>Привет! Это ROXY — твоя AI-студия.</b>\n\n"
        "Создавай фото, видео и музыку, сохраняй работы в профиль, публикуй в ленту "
        "и приглашай друзей через партнёрский кабинет.\n\n"
        "Нажми кнопку ниже, чтобы открыть приложение. Если нужна помощь — напиши в поддержку.",
        reply_markup=app_launcher_menu(route=route, start_payload=payload),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "app:unavailable")
async def app_unavailable(callback: CallbackQuery) -> None:
    """Fail closed without falling back to the retired text-bot product UI."""
    await callback.answer(
        "ROXY временно недоступна. Попробуй открыть приложение чуть позже.",
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


@router.message(F.text == QUICK_SUPPORT_TEXT)
async def support_message(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """Give users a direct human support contact without opening a text-menu clone."""
    if message.from_user is None:
        return
    await state.clear()
    await UserService.get_or_create(session, message.from_user)
    await session.commit()
    await message.answer(
        f"Поддержка ROXY: {SUPPORT_USERNAME}\n\n"
        "Напишите туда, если нужна помощь с генерацией, оплатой или публикацией.",
        reply_markup=app_launcher_menu(route="home"),
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
    await _send_launcher(message, route="home", payload=None)
