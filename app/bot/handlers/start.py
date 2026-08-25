from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.feed import handle_deep_link
from app.bot.keyboards import (
    QUICK_MENU_TEXT,
    back_menu,
    balance_menu,
    main_menu,
    onboarding_menu,
    quick_menu,
)
from app.core.config import settings
from app.db.models import User, Wallet
from app.services.account_profile import AccountProfileService
from app.services.feed import FeedNotFoundError, FeedService
from app.services.feed_links import FeedDeepLink, parse_feed_deep_link, start_payload
from app.services.onboarding import OnboardingService
from app.services.partner import PartnerService
from app.services.partner_wallet import PartnerWalletTransferService
from app.services.referrals import ReferralService
from app.services.users import UserService

router = Router(name="start")


def _start_link(text: str | None) -> FeedDeepLink | None:
    return parse_feed_deep_link(start_payload(text))


def _parse_inviter(text: str | None) -> int | None:
    link = _start_link(text)
    if link is None or link.action != "ref":
        return None
    return link.referral_telegram_id


async def _validated_inviter(
    session: AsyncSession,
    link: FeedDeepLink | None,
) -> int | None:
    if link is None:
        return None
    if link.action == "ref":
        return link.referral_telegram_id
    if link.action == "posts" and link.profile_referral_code:
        if str(link.referral_telegram_id) != link.profile_referral_code:
            return None
        try:
            author = await FeedService.author_by_referral_code(
                session,
                link.profile_referral_code,
            )
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


async def _balances(session: AsyncSession, user_id) -> tuple[object, object]:  # type: ignore[no-untyped-def]
    wallet = await session.get(Wallet, user_id)
    partner = await PartnerWalletTransferService.accounting(session, user_id)
    rox_balance = wallet.balance if wallet else 0
    partner_rub = partner["available"]
    return rox_balance, partner_rub


async def _send_quick_menu(message: Message) -> None:
    await message.answer(
        "Быстрый доступ ROXY",
        reply_markup=quick_menu(),
    )


async def _send_main_menu(
    message: Message,
    user,
    session: AsyncSession,
    *,
    start_payload_value: str | None = None,
) -> None:  # type: ignore[no-untyped-def]
    await message.answer(
        "<b>ROXY ✨</b>\n"
        "<b>Создавай. Вдохновляй.</b>\n\n"
        "👇<b>Нажми, чтобы открыть ROXY</b>",
        reply_markup=main_menu(start_payload=start_payload_value),
        parse_mode="HTML",
    )


async def _profile_text(session: AsyncSession, user) -> str:  # type: ignore[no-untyped-def]
    overview = await AccountProfileService.overview(session, user)
    return AccountProfileService.text(overview)


async def _balance_text(session: AsyncSession, user_id) -> str:  # type: ignore[no-untyped-def]
    rox_balance, partner_rub = await _balances(session, user_id)
    return (
        "💎 Мои ROX\n\n"
        f"Баланс ROX: {rox_balance}\n"
        "Бонусы и пополнения сразу зачисляются на этот баланс.\n\n"
        f"💰 Заработок партнёра: {partner_rub} ₽\n"
        "Это доход с реальных пополнений 1-й и 2-й линии. Его можно перевести в ROX или оформить выплату.\n\n"
        "1 ROX = 1 ₽\n"
        f"Вывод деньгами от {settings.partner_min_withdrawal_rub} ₽."
    )


@router.message(CommandStart())
async def start(
    message: Message,
    session: AsyncSession,
    state: FSMContext,
    redis: Redis,
) -> None:
    if message.from_user is None:
        return
    await state.clear()
    payload = start_payload(message.text)
    link = parse_feed_deep_link(payload)
    user = await UserService.get_or_create(
        session,
        message.from_user,
        inviter_telegram_id=await _validated_inviter(session, link),
    )
    await session.flush()
    if not await OnboardingService.is_complete(session, user.id):
        if payload:
            await state.update_data(pending_start_payload=payload)
        body = settings.onboarding_body.strip()
        text = settings.onboarding_title.strip() or "Добро пожаловать в ROXY"
        if body:
            text = f"{text}\n\n{body}"
        await message.answer(text, reply_markup=onboarding_menu())
        return

    await _send_quick_menu(message)
    if link is not None and link.action != "ref":
        if await handle_deep_link(
            message,
            user_id=user.id,
            link=link,
            session=session,
            redis=redis,
        ):
            return
    await _send_main_menu(message, user, session, start_payload_value=payload if link else None)


@router.message(F.text == QUICK_MENU_TEXT)
async def quick_menu_message(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await state.clear()
    user = await UserService.get_or_create(session, message.from_user)
    await _send_main_menu(message, user, session)


@router.callback_query(F.data == "nav:main")
async def nav_main(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    await state.clear()
    await callback.answer()
    if callback.message:
        await _send_main_menu(callback.message, user, session)


@router.callback_query(F.data == "onboarding_complete")
async def onboarding_complete(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    redis: Redis,
) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    pending = await state.get_data()
    await OnboardingService.complete(session, user.id)
    await session.commit()
    await callback.answer("Готово")
    payload = str(pending.get("pending_start_payload") or "")
    await state.clear()
    link = parse_feed_deep_link(payload)
    if callback.message:
        await _send_quick_menu(callback.message)
        if link is not None and link.action != "ref":
            if await handle_deep_link(
                callback.message,
                user_id=user.id,
                link=link,
                session=session,
                redis=redis,
            ):
                return
        await _send_main_menu(
            callback.message,
            user,
            session,
            start_payload_value=payload if link else None,
        )


@router.message(Command("balance"))
async def balance_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService.get_or_create(session, message.from_user)
    await message.answer(await _balance_text(session, user.id), reply_markup=balance_menu())


@router.callback_query(F.data == "balance")
async def balance_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            await _balance_text(session, user.id),
            reply_markup=balance_menu(),
        )


@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    text = await _profile_text(session, user)
    await session.commit()
    await callback.answer()
    if callback.message:
        await callback.message.answer(text, reply_markup=back_menu())


@router.callback_query(F.data == "referrals")
async def referrals_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    stats = await ReferralService.stats(session, user.id)
    partner = await PartnerWalletTransferService.accounting(session, user.id)
    referral_link = PartnerService.referral_link(user.telegram_id) or "недоступна"
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            "👥 Партнёры ROXY\n\n"
            f"🎁 {settings.start_balance_rox} ROX — при регистрации, сразу в баланс\n"
            f"👤 +{settings.invite_bonus_rox} ROX — за приглашённого, сразу в баланс\n"
            f"🔁 +{settings.prompt_repeat_bonus_rox} ROX — за повтор промпта, сразу в баланс\n\n"
            f"💰 {settings.referral_first_percent}% — заработок с пополнений 1-й линии\n"
            f"💰 {settings.referral_second_percent}% — заработок с пополнений 2-й линии\n"
            f"Доступно: {partner['available']} ₽\n"
            f"Вывод деньгами от {settings.partner_min_withdrawal_rub} ₽ или перевод в ROX без смешивания балансов.\n\n"
            f"1 линия: {stats['first_line']} · 2 линия: {stats['second_line']}\n\n"
            f"Реферальная ссылка: {referral_link}",
            reply_markup=back_menu(),
        )


@router.message(Command("profile"))
async def profile_command(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService.get_or_create(session, message.from_user)
    text = await _profile_text(session, user)
    await session.commit()
    await message.answer(text, reply_markup=back_menu())
