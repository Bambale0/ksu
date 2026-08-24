from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import QUICK_SUPPORT_TEXT, back_menu
from app.bot.support_links import normalize_direct_support_url
from app.core.config import settings
from app.db.models import SupportMessage, SupportTicket
from app.services.users import UserService

router = Router(name="support")


class SupportFlow(StatesGroup):
    waiting_topic = State()
    waiting_message = State()


def _direct_support_url() -> str | None:
    return normalize_direct_support_url(settings.support_telegram_url)


def _direct_support_markup(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🆘 Написать в поддержку", url=url)],
        ]
    )


async def _start_ticket(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SupportFlow.waiting_topic)
    await message.answer(
        "Напиши тему обращения: оплата, ROX, генерация, промокод, партнёрка или другое.",
        reply_markup=back_menu(),
    )


async def _show_direct_support(message: Message, state: FSMContext) -> bool:
    url = _direct_support_url()
    if not url:
        return False
    await state.clear()
    await message.answer(
        "Поддержка ROXY — напиши напрямую оператору:",
        reply_markup=_direct_support_markup(url),
    )
    return True


@router.message(F.text == QUICK_SUPPORT_TEXT)
async def quick_support(message: Message, state: FSMContext) -> None:
    if await _show_direct_support(message, state):
        return
    await _start_ticket(message, state)


@router.callback_query(F.data == "support")
async def support_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if await _show_direct_support(callback.message, state):
        return
    await _start_ticket(callback.message, state)


@router.callback_query(F.data == "support:back_topic")
async def support_back_topic(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SupportFlow.waiting_topic)
    await state.update_data(topic=None)
    if callback.message:
        await callback.message.answer(
            "Напиши тему обращения: оплата, ROX, генерация, промокод, партнёрка или другое.",
            reply_markup=back_menu(),
        )


@router.message(SupportFlow.waiting_topic)
async def support_topic(message: Message, state: FSMContext) -> None:
    await state.update_data(topic=(message.text or "другое")[:64])
    await state.set_state(SupportFlow.waiting_message)
    await message.answer(
        "Теперь опиши проблему одним сообщением.",
        reply_markup=back_menu("support:back_topic"),
    )


@router.message(SupportFlow.waiting_message)
async def support_message(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    user = await UserService.get_or_create(session, message.from_user)
    ticket = SupportTicket(user_id=user.id, topic=str(data.get("topic") or "другое"))
    session.add(ticket)
    await session.flush()
    session.add(
        SupportMessage(
            ticket_id=ticket.id,
            user_id=user.id,
            body=message.text or "[не текстовое сообщение]",
        )
    )
    await state.clear()
    await message.answer(
        f"✅ Обращение создано: {ticket.id}",
        reply_markup=back_menu(),
    )
