from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.generations import GenerationService
from app.services.users import UserService
from app.services.wallet import InsufficientBalanceError

router = Router(name="generation")
DEMO_GENERATION_COST = Decimal("10")


class GenerationFlow(StatesGroup):
    waiting_prompt = State()


@router.callback_query(F.data == "create")
async def generation_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(GenerationFlow.waiting_prompt)
    if callback.message:
        await callback.message.answer("Отправь промпт для генерации. Базовая стоимость: 10 ROX.")


@router.message(GenerationFlow.waiting_prompt)
async def generation_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis: Redis,
) -> None:
    if message.from_user is None or not message.text:
        await message.answer("Нужен текстовый промпт.")
        return
    user = await UserService.get_or_create(session, message.from_user)
    try:
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user.id,
            kind="text_to_image",
            prompt=message.text,
            cost_rox=DEMO_GENERATION_COST,
        )
    except InsufficientBalanceError:
        await message.answer("Недостаточно ROX. Пополни баланс и повтори.")
        return
    await state.clear()
    await message.answer(f"⏳ Задача поставлена в очередь: {generation.id}")
