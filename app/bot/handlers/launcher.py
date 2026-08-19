from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import app_launcher_menu
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
    # Remove the persistent reply keyboard shipped by the previous text-bot UX.
    # A second message contains the only supported customer navigation control.
    await message.answer("ROXY теперь работает через приложение.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "<b>ROXY ✨</b>\nВсе функции — генерации, баланс, история, профиль и поддержка — внутри Mini App.",
        reply_markup=app_launcher_menu(route=route, start_payload=payload),
        parse_mode="HTML",
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
