from __future__ import annotations

import os

import httpx
from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards import QUICK_TEST_TEXT, quick_menu
from app.providers.nexus import NexusClient, NexusProviderError
from app.services.admin_security import parse_bootstrap_ids

router = Router(name="nexus-admin-test")


class NexusTestStates(StatesGroup):
    prompt = State()


def _is_env_admin(telegram_id: int | None) -> bool:
    return telegram_id is not None and telegram_id in parse_bootstrap_ids()


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")]
        ]
    )


async def _deny(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Тестовый режим доступен только администраторам.")


@router.message(F.text == QUICK_TEST_TEXT)
async def nexus_test_start(message: Message, state: FSMContext) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not _is_env_admin(telegram_id):
        await _deny(message, state)
        return

    if not os.environ.get("NEXUS_API_KEY", "").strip():
        await state.clear()
        await message.answer(
            "NexusAPI пока не настроен: добавьте NEXUS_API_KEY в env сервиса бота.",
            reply_markup=quick_menu(is_admin=True),
        )
        return

    await state.set_state(NexusTestStates.prompt)
    await message.answer(
        "🧪 <b>NexusAPI · Nano Banana Pro</b>\n\n"
        "Пришлите текстовый промпт. Тест запускается напрямую через NexusAPI "
        "с model_name=nano-banana-pro, 2K и форматом 1:1.\n\n"
        "Тестовый запуск не списывает ROX у пользователя, но расходует баланс NexusAPI.",
        parse_mode="HTML",
        reply_markup=_cancel_keyboard(),
    )


@router.callback_query(F.data == "nexus-test:cancel")
async def nexus_test_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_env_admin(callback.from_user.id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.answer("Тест отменён")
    if isinstance(callback.message, Message):
        await callback.message.answer("Тестовый режим закрыт.", reply_markup=quick_menu(is_admin=True))


@router.message(NexusTestStates.prompt)
async def nexus_test_generate(message: Message, state: FSMContext) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not _is_env_admin(telegram_id):
        await _deny(message, state)
        return

    prompt = str(message.text or "").strip()
    if len(prompt) < 3:
        await message.answer("Промпт слишком короткий. Пришлите текст от 3 символов.")
        return
    if len(prompt) > 6000:
        await message.answer("Промпт слишком длинный. Максимум для теста — 6000 символов.")
        return

    api_key = os.environ.get("NEXUS_API_KEY", "").strip()
    if not api_key:
        await state.clear()
        await message.answer(
            "NEXUS_API_KEY пропал из env. Тест не запущен.",
            reply_markup=quick_menu(is_admin=True),
        )
        return

    await state.clear()
    status_message = await message.answer("⏳ Отправляю Nano Banana Pro в NexusAPI…")
    client = NexusClient(
        api_key=api_key,
        base_url=os.environ.get("NEXUS_API_BASE_URL", "https://nexusapi.dev"),
    )
    task_id = ""
    try:
        task_id = await client.create_nano_banana_pro(
            prompt=prompt,
            aspect_ratio="1:1",
            image_size="2K",
        )
        await status_message.edit_text(
            f"⏳ NexusAPI принял задачу {task_id}. Жду результат Nano Banana Pro…"
        )
        task = await client.wait_for_task(task_id, timeout_seconds=90, poll_interval_seconds=2)
        image_url = task.image_urls[0]
        caption = (
            "✅ NexusAPI · Nano Banana Pro\n"
            f"Task: {task.task_id}\n"
            "Параметры: 2K · 1:1"
        )
        try:
            await message.answer_photo(
                photo=image_url,
                caption=caption,
                reply_markup=quick_menu(is_admin=True),
            )
        except TelegramAPIError:
            await message.answer(
                f"{caption}\n\nРезультат: {image_url}",
                reply_markup=quick_menu(is_admin=True),
            )
        await status_message.delete()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        await status_message.edit_text(
            f"❌ NexusAPI вернул HTTP {status}."
            + (f"\nTask: {task_id}" if task_id else "")
        )
        await message.answer("Тест завершён с ошибкой.", reply_markup=quick_menu(is_admin=True))
    except (httpx.HTTPError, NexusProviderError) as exc:
        await status_message.edit_text(
            "❌ NexusAPI: " + str(exc)[:1200] + (f"\nTask: {task_id}" if task_id else "")
        )
        await message.answer("Тест завершён с ошибкой.", reply_markup=quick_menu(is_admin=True))
    finally:
        await client.aclose()
