from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import main_menu
from app.db.models import Wallet
from app.services.referrals import ReferralService
from app.services.users import UserService

router = Router(name="start")


def _parse_inviter(text: str | None) -> int | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].startswith("ref_"):
        return None
    try:
        return int(parts[1][4:])
    except ValueError:
        return None


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService.get_or_create(
        session,
        message.from_user,
        inviter_telegram_id=_parse_inviter(message.text),
    )
    await session.flush()
    wallet = await session.get(Wallet, user.id)
    balance = wallet.balance if wallet else 0
    await message.answer(
        f"Привет, {user.first_name}!\n\nБаланс: {balance} ROX\nВыбери действие:",
        reply_markup=main_menu(),
    )


@router.message(Command("balance"))
async def balance_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService.get_or_create(session, message.from_user)
    wallet = await session.get(Wallet, user.id)
    await message.answer(f"💎 Баланс: {wallet.balance if wallet else 0} ROX")


@router.callback_query(F.data == "balance")
async def balance_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None:
        return
    user = await UserService.get_or_create(session, callback.from_user)
    wallet = await session.get(Wallet, user.id)
    await callback.answer()
    if callback.message:
        await callback.message.answer(f"💎 Баланс: {wallet.balance if wallet else 0} ROX")


@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            f"👤 Профиль\nID: {user.telegram_id}\nUsername: @{user.username or '—'}"
        )


@router.callback_query(F.data == "referrals")
async def referrals_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    stats = await ReferralService.stats(session, user.id)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "🤝 Партнёрская программа\n"
            f"1 линия: {stats['first_line']}\n"
            f"2 линия: {stats['second_line']}\n"
            f"Доступно: {stats['available']}\n"
            f"В ожидании: {stats['pending']}\n\n"
            f"Реферальная ссылка: https://t.me/{(await callback.bot.me()).username}?start=ref_{user.telegram_id}"
        )


@router.message(Command("profile"))
async def profile_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService.get_or_create(session, message.from_user)
    await message.answer(f"👤 ID: {user.telegram_id}\nUsername: @{user.username or '—'}")
