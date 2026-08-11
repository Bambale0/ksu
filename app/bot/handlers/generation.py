from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError
from app.services.users import UserService
from app.services.wallet import InsufficientBalanceError

router = Router(name="generation")
DEFAULT_MODEL_ID = "nano-banana-2"


class GenerationFlow(StatesGroup):
    waiting_prompt = State()


@router.callback_query(F.data == "create")
async def generation_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(GenerationFlow.waiting_prompt)
    if callback.message:
        await callback.message.answer(
            "Отправь промпт для генерации. Цена рассчитывается сервером по выбранной модели."
        )


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
            model_id=DEFAULT_MODEL_ID,
            prompt=message.text,
        )
    except InsufficientBalanceError:
        await message.answer("Недостаточно ROX. Пополни баланс и повтори.")
        return
    except InvalidModelParametersError as exc:
        await message.answer(f"Параметры генерации не приняты: {exc}")
        return
    await state.clear()
    await message.answer(
        f"⏳ Задача поставлена в очередь: {generation.id}\n"
        f"Списано: {generation.cost_rox} ROX"
    )
