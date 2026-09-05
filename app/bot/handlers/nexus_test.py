from __future__ import annotations

import base64
import os
import uuid
from io import BytesIO
from typing import Any

import httpx
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.keyboards import QUICK_TEST_TEXT, quick_menu
from app.providers.nexus import (
    NANO_BANANA_PRO_ASPECT_RATIOS,
    NANO_BANANA_PRO_MAX_REFERENCES,
    NexusClient,
    NexusProviderError,
)
from app.services.admin_security import parse_bootstrap_ids

router = Router(name="nexus-admin-test")

NEXUS_TEST_ASPECT_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16")
NEXUS_TEST_IMAGE_SIZES = ("2K", "4K")
MAX_REFERENCE_FILE_BYTES = 8 * 1024 * 1024
MAX_REFERENCE_TOTAL_BYTES = 24 * 1024 * 1024


class NexusTestStates(StatesGroup):
    references = State()
    prompt = State()
    aspect_ratio = State()
    image_size = State()


def _is_env_admin(telegram_id: int | None) -> bool:
    return telegram_id is not None and telegram_id in parse_bootstrap_ids()


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")]
        ]
    )


def _references_keyboard(count: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if count > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Продолжить · {count}/{NANO_BANANA_PRO_MAX_REFERENCES}",
                    callback_data="nexus-test:refs:done",
                )
            ]
        )
        rows.append(
            [InlineKeyboardButton(text="Очистить референсы", callback_data="nexus-test:refs:clear")]
        )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _aspect_ratio_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="1:1", callback_data="nexus-test:ratio:1:1"),
            InlineKeyboardButton(text="4:3", callback_data="nexus-test:ratio:4:3"),
            InlineKeyboardButton(text="3:4", callback_data="nexus-test:ratio:3:4"),
        ],
        [
            InlineKeyboardButton(text="16:9", callback_data="nexus-test:ratio:16:9"),
            InlineKeyboardButton(text="9:16", callback_data="nexus-test:ratio:9:16"),
        ],
        [InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _image_size_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="2K", callback_data="nexus-test:size:2K"),
                InlineKeyboardButton(text="4K", callback_data="nexus-test:size:4K"),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")],
        ]
    )


async def _deny(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Тестовый режим доступен только администраторам.")


def _message_reference(message: Message) -> dict[str, Any] | None:
    if message.photo:
        photo = message.photo[-1]
        return {
            "file_id": photo.file_id,
            "mime_type": "image/jpeg",
            "file_size": int(photo.file_size or 0),
        }
    document = message.document
    if document and str(document.mime_type or "").lower().startswith("image/"):
        return {
            "file_id": document.file_id,
            "mime_type": str(document.mime_type or "image/jpeg").lower(),
            "file_size": int(document.file_size or 0),
        }
    return None


def _data_url(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


async def _download_references(bot: Bot, references: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    total = 0
    for reference in references:
        file_size = int(reference.get("file_size") or 0)
        if file_size > MAX_REFERENCE_FILE_BYTES:
            raise NexusProviderError("Один из референсов больше 8 МБ")
        buffer = BytesIO()
        await bot.download(str(reference.get("file_id") or ""), destination=buffer)
        content = buffer.getvalue()
        if not content:
            raise NexusProviderError("Не удалось скачать один из референсов из Telegram")
        if len(content) > MAX_REFERENCE_FILE_BYTES:
            raise NexusProviderError("Один из референсов больше 8 МБ")
        total += len(content)
        if total > MAX_REFERENCE_TOTAL_BYTES:
            raise NexusProviderError("Суммарный размер референсов больше 24 МБ")
        values.append(_data_url(content, str(reference.get("mime_type") or "image/jpeg")))
    return values


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

    await state.set_state(NexusTestStates.references)
    await state.set_data(
        {
            "references": [],
            "idempotency_key": f"ksu-nexus-test:{telegram_id}:{uuid.uuid4()}",
            "running": False,
        }
    )
    await message.answer(
        "🧪 <b>NexusAPI · Nano Banana Pro</b>\n\n"
        "Пришлите от <b>1 до 4 изображений-референсов</b> — обычным фото или файлом. "
        "Можно отправлять по одному. После загрузки нажмите «Продолжить».\n\n"
        "Дальше бот попросит промпт, aspect ratio и качество <b>2K / 4K</b>.\n\n"
        "Тестовый запуск не списывает ROX у пользователя, но расходует баланс NexusAPI.",
        parse_mode="HTML",
        reply_markup=_references_keyboard(0),
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


@router.callback_query(NexusTestStates.references, F.data == "nexus-test:refs:clear")
async def nexus_test_clear_references(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_env_admin(callback.from_user.id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    await state.update_data(references=[])
    await callback.answer("Референсы очищены")
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=_references_keyboard(0))
    if data.get("running"):
        await state.update_data(running=False)


@router.callback_query(NexusTestStates.references, F.data == "nexus-test:refs:done")
async def nexus_test_references_done(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_env_admin(callback.from_user.id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    references = list(data.get("references") or [])
    if not references:
        await callback.answer("Сначала добавьте хотя бы один референс", show_alert=True)
        return
    await state.set_state(NexusTestStates.prompt)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"Референсов: {len(references)}. Теперь пришлите текстовый промпт для Nano Banana Pro.",
            reply_markup=_cancel_keyboard(),
        )


@router.message(NexusTestStates.references)
async def nexus_test_collect_reference(message: Message, state: FSMContext) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not _is_env_admin(telegram_id):
        await _deny(message, state)
        return

    reference = _message_reference(message)
    if reference is None:
        await message.answer(
            "Нужен референс-картинка: отправьте фото или изображение как файл.",
            reply_markup=_references_keyboard(len((await state.get_data()).get("references") or [])),
        )
        return
    if int(reference.get("file_size") or 0) > MAX_REFERENCE_FILE_BYTES:
        await message.answer("Этот референс больше 8 МБ. Пришлите изображение поменьше.")
        return

    data = await state.get_data()
    references = list(data.get("references") or [])
    if len(references) >= NANO_BANANA_PRO_MAX_REFERENCES:
        await message.answer(
            "У Nano Banana Pro в NexusAPI максимум 4 референса. Нажмите «Продолжить».",
            reply_markup=_references_keyboard(len(references)),
        )
        return
    references.append(reference)
    await state.update_data(references=references)
    await message.answer(
        f"✅ Референс добавлен · {len(references)}/{NANO_BANANA_PRO_MAX_REFERENCES}",
        reply_markup=_references_keyboard(len(references)),
    )


@router.message(NexusTestStates.prompt)
async def nexus_test_prompt(message: Message, state: FSMContext) -> None:
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

    await state.update_data(prompt=prompt)
    await state.set_state(NexusTestStates.aspect_ratio)
    await message.answer(
        "Выберите aspect ratio результата:",
        reply_markup=_aspect_ratio_keyboard(),
    )


@router.callback_query(NexusTestStates.aspect_ratio, F.data.startswith("nexus-test:ratio:"))
async def nexus_test_aspect_ratio(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_env_admin(callback.from_user.id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    aspect_ratio = str(callback.data or "").removeprefix("nexus-test:ratio:")
    if aspect_ratio not in NEXUS_TEST_ASPECT_RATIOS or aspect_ratio not in NANO_BANANA_PRO_ASPECT_RATIOS:
        await callback.answer("Неподдерживаемый aspect ratio", show_alert=True)
        return
    await state.update_data(aspect_ratio=aspect_ratio)
    await state.set_state(NexusTestStates.image_size)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"Формат: {aspect_ratio}. Выберите качество:",
            reply_markup=_image_size_keyboard(),
        )


@router.callback_query(NexusTestStates.image_size, F.data.startswith("nexus-test:size:"))
async def nexus_test_generate(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not _is_env_admin(callback.from_user.id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Не удалось открыть сообщение теста", show_alert=True)
        return

    image_size = str(callback.data or "").removeprefix("nexus-test:size:")
    if image_size not in NEXUS_TEST_IMAGE_SIZES:
        await callback.answer("Выберите 2K или 4K", show_alert=True)
        return

    data = await state.get_data()
    if data.get("running"):
        await callback.answer("Эта задача уже запускается")
        return
    references = list(data.get("references") or [])
    prompt = str(data.get("prompt") or "").strip()
    aspect_ratio = str(data.get("aspect_ratio") or "")
    idempotency_key = str(data.get("idempotency_key") or "").strip()
    if not references or not prompt or aspect_ratio not in NEXUS_TEST_ASPECT_RATIOS:
        await state.clear()
        await callback.answer("Данные теста устарели. Запустите 🧪 Тест заново.", show_alert=True)
        return

    api_key = os.environ.get("NEXUS_API_KEY", "").strip()
    if not api_key:
        await state.clear()
        await callback.answer("NEXUS_API_KEY не настроен", show_alert=True)
        await callback.message.answer(
            "NEXUS_API_KEY пропал из env. Тест не запущен.",
            reply_markup=quick_menu(is_admin=True),
        )
        return

    await state.update_data(running=True, image_size=image_size)
    await callback.answer("Запускаю")
    status_message = await callback.message.answer(
        f"⏳ Готовлю {len(references)} реф. · {aspect_ratio} · {image_size}…"
    )
    client = NexusClient(
        api_key=api_key,
        base_url=os.environ.get("NEXUS_API_BASE_URL", "https://nexusapi.dev"),
    )
    task_id = ""
    try:
        image_urls = await _download_references(bot, references)
        task_id = await client.create_nano_banana_pro(
            prompt=prompt,
            image_urls=image_urls,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            idempotency_key=idempotency_key or None,
        )
        await status_message.edit_text(
            f"⏳ NexusAPI принял задачу {task_id}. Жду Nano Banana Pro · {image_size} · {aspect_ratio}…"
        )
        task = await client.wait_for_task(task_id, timeout_seconds=240, poll_interval_seconds=2)
        image_url = task.image_urls[0]
        caption = (
            "✅ NexusAPI · Nano Banana Pro\n"
            f"Task: {task.task_id}\n"
            f"Референсы: {len(references)}\n"
            f"Параметры: {image_size} · {aspect_ratio}"
        )
        try:
            await callback.message.answer_photo(
                photo=image_url,
                caption=caption,
                reply_markup=quick_menu(is_admin=True),
            )
        except TelegramAPIError:
            await callback.message.answer(
                f"{caption}\n\nРезультат: {image_url}",
                reply_markup=quick_menu(is_admin=True),
            )
        try:
            await status_message.delete()
        except TelegramAPIError:
            pass
        await state.clear()
    except httpx.HTTPStatusError as exc:
        await state.clear()
        status = exc.response.status_code
        await status_message.edit_text(
            f"❌ NexusAPI вернул HTTP {status}."
            + (f"\nTask: {task_id}" if task_id else "")
        )
        await callback.message.answer("Тест завершён с ошибкой.", reply_markup=quick_menu(is_admin=True))
    except (httpx.HTTPError, NexusProviderError, TelegramAPIError) as exc:
        await state.clear()
        await status_message.edit_text(
            "❌ NexusAPI: " + str(exc)[:1200] + (f"\nTask: {task_id}" if task_id else "")
        )
        await callback.message.answer("Тест завершён с ошибкой.", reply_markup=quick_menu(is_admin=True))
    finally:
        await client.aclose()
