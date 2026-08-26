from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import back_menu, onboarding_menu
from app.services.abuse_protection import ResourcePolicyError
from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError
from app.services.onboarding import OnboardingService
from app.services.users import UserService
from app.services.wallet import InsufficientBalanceError

router = Router(name="generation")
DEFAULT_MODEL_ID = "nano-banana-2"


class GenerationFlow(StatesGroup):
    waiting_prompt = State()


@router.callback_query(F.data == "create")
async def generation_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await UserService.get_or_create(session, callback.from_user)
    if not await OnboardingService.is_complete(session, user.id):
        await callback.answer("Сначала завершите вводный экран", show_alert=True)
        if callback.message:
            await callback.message.answer(
                "Чтобы создавать контент, сначала нажмите «Начать».",
                reply_markup=onboarding_menu(),
            )
        return
    await callback.answer()
    await state.set_state(GenerationFlow.waiting_prompt)
    if callback.message:
        await callback.message.answer(
            "Опиши, что нужно создать. Стоимость покажем перед запуском.",
            reply_markup=back_menu(),
        )


@router.message(GenerationFlow.waiting_prompt)
async def generation_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    redis: Redis,
) -> None:
    if message.from_user is None or not message.text:
        await message.answer("Нужно текстовое описание.", reply_markup=back_menu())
        return
    user = await UserService.get_or_create(session, message.from_user)
    if not await OnboardingService.is_complete(session, user.id):
        await state.clear()
        await message.answer(
            "Версия вводного экрана обновилась. Нажмите «Начать», затем запустите генерацию снова.",
            reply_markup=onboarding_menu(),
        )
        return
    try:
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user.id,
            model_id=DEFAULT_MODEL_ID,
            prompt=message.text,
        )
    except InsufficientBalanceError:
        await message.answer(
            "Недостаточно кредитов. Пополни баланс и повтори.",
            reply_markup=back_menu(),
        )
        return
    except ResourcePolicyError as exc:
        await message.answer(
            f"Сейчас нельзя запустить ещё одну работу: {exc}. "
            f"Повтори примерно через {exc.retry_after} сек.",
            reply_markup=back_menu(),
        )
        return
    except InvalidModelParametersError as exc:
        await message.answer(
            f"Проверьте описание и настройки: {exc}",
            reply_markup=back_menu(),
        )
        return
    await state.clear()
    await message.answer(
        f"⏳ Задача поставлена в очередь: {generation.id}\n"
        f"Списано: {generation.cost_rox} кр.",
        reply_markup=back_menu(),
    )
