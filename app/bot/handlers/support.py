from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SupportMessage, SupportTicket
from app.services.users import UserService

router = Router(name="support")


class SupportFlow(StatesGroup):
    waiting_topic = State()
    waiting_message = State()


@router.callback_query(F.data == "support")
async def support_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(SupportFlow.waiting_topic)
    if callback.message:
        await callback.message.answer(
            "Напиши тему обращения: оплата, ROX, генерация, промокод, партнёрка или другое."
        )


@router.message(SupportFlow.waiting_topic)
async def support_topic(message: Message, state: FSMContext) -> None:
    await state.update_data(topic=(message.text or "другое")[:64])
    await state.set_state(SupportFlow.waiting_message)
    await message.answer("Теперь опиши проблему одним сообщением.")


@router.message(SupportFlow.waiting_message)
async def support_message(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    user = await UserService.get_or_create(session, message.from_user)
    ticket = SupportTicket(user_id=user.id, topic=str(data.get("topic", "другое")))
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
    await message.answer(f"✅ Обращение создано: {ticket.id}")
