from __future__ import annotations

import uuid
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin import _admin_account
from app.bot.keyboards import QUICK_MENU_TEXT, QUICK_SUPPORT_TEXT, QUICK_TEST_TEXT, quick_menu
from app.core.config import settings
from app.providers.nexus import NANO_BANANA_PRO_ASPECT_RATIOS, NANO_BANANA_PRO_MAX_REFERENCES
from app.services.admin_security import parse_bootstrap_ids
from app.services.nexus_admin_tasks import MAX_REFERENCE_FILE_BYTES, NexusAdminTaskService

router = Router(name="nexus-admin-test")

NEXUS_TEST_ASPECT_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16")
NEXUS_TEST_IMAGE_SIZES = ("2K", "4K")

# Bottom-bar navigation shortcuts must never be swallowed by the test FSM.
# Messages matching these texts are handled by the customer launcher instead.
NEXUS_TEST_EXIT_TEXTS = frozenset({QUICK_MENU_TEXT, QUICK_SUPPORT_TEXT, QUICK_TEST_TEXT})


class NexusTestStates(StatesGroup):
    references = State()
    prompt = State()
    aspect_ratio = State()
    image_size = State()


async def _is_admin(session: AsyncSession, telegram_id: int | None) -> bool:
    if telegram_id is None:
        return False
    if telegram_id in parse_bootstrap_ids():
        return True
    return await _admin_account(session, telegram_id) is not None


async def _state_authorized(
    state: FSMContext,
    session: AsyncSession,
    telegram_id: int | None,
) -> bool:
    if telegram_id is None:
        return False
    data = await state.get_data()
    if int(data.get("admin_telegram_id") or 0) != telegram_id:
        return False
    # Authorization is live, not a snapshot: a deactivated DB admin must lose
    # access before any later step can spend provider balance.
    return await _is_admin(session, telegram_id)


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
    return InlineKeyboardMarkup(
        inline_keyboard=[
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
    )


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


@router.message(F.text == QUICK_TEST_TEXT)
async def nexus_test_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not await _is_admin(session, telegram_id):
        await _deny(message, state)
        return

    if not settings.nexus_api_key.strip():
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
            "admin_telegram_id": telegram_id,
        }
    )
    await message.answer(
        "🧪 Nano Banana Pro · NexusAPI\n\n"
        f"Пришлите от 1 до {NANO_BANANA_PRO_MAX_REFERENCES} фото-референсов по одному сообщению. "
        "Когда закончите, нажмите «Продолжить».\n\n"
        "Тестовый режим использует отдельную NexusAPI генерацию и не списывает ROX.",
        reply_markup=_references_keyboard(0),
    )


@router.message(NexusTestStates.references, ~F.text.in_(NEXUS_TEST_EXIT_TEXTS), ~F.text.startswith("/"))
async def nexus_test_reference(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not await _state_authorized(state, session, telegram_id):
        await _deny(message, state)
        return

    reference = _message_reference(message)
    if reference is None:
        await message.answer(
            "Пришлите фото или изображение-файл.",
            reply_markup=_references_keyboard(len((await state.get_data()).get("references") or [])),
        )
        return
    if int(reference["file_size"] or 0) > MAX_REFERENCE_FILE_BYTES:
        await message.answer(
            f"Файл слишком большой. Лимит — {MAX_REFERENCE_FILE_BYTES // (1024 * 1024)} МБ.",
            reply_markup=_references_keyboard(len((await state.get_data()).get("references") or [])),
        )
        return

    data = await state.get_data()
    references = list(data.get("references") or [])
    if len(references) >= NANO_BANANA_PRO_MAX_REFERENCES:
        await message.answer(
            f"Уже добавлено максимум {NANO_BANANA_PRO_MAX_REFERENCES} референса.",
            reply_markup=_references_keyboard(len(references)),
        )
        return
    references.append(reference)
    await state.update_data(references=references)
    await message.answer(
        f"Референс добавлен: {len(references)}/{NANO_BANANA_PRO_MAX_REFERENCES}",
        reply_markup=_references_keyboard(len(references)),
    )


@router.callback_query(F.data == "nexus-test:refs:clear")
async def nexus_test_clear_references(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _state_authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.update_data(references=[])
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=_references_keyboard(0))
    await callback.answer("Референсы очищены")


@router.callback_query(F.data == "nexus-test:refs:done")
async def nexus_test_references_done(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _state_authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    references = list((await state.get_data()).get("references") or [])
    if not references:
        await callback.answer("Добавьте хотя бы один референс", show_alert=True)
        return
    await state.set_state(NexusTestStates.prompt)
    if callback.message:
        await callback.message.answer(
            "Введите промпт для Nano Banana Pro.",
            reply_markup=_cancel_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "nexus-test:cancel")
async def nexus_test_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer("Тест отменён")
    if callback.message:
        await callback.message.answer(
            "Тест отменён. Вы вышли из тестового режима.",
            reply_markup=quick_menu(is_admin=True),
        )


@router.message(NexusTestStates.prompt, ~F.text.in_(NEXUS_TEST_EXIT_TEXTS), ~F.text.startswith("/"))
async def nexus_test_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not await _state_authorized(state, session, telegram_id):
        await _deny(message, state)
        return
    prompt = str(message.text or message.caption or "").strip()
    if not prompt:
        await message.answer("Промпт не должен быть пустым.", reply_markup=_cancel_keyboard())
        return
    await state.update_data(prompt=prompt)
    await state.set_state(NexusTestStates.aspect_ratio)
    await message.answer("Выберите соотношение сторон:", reply_markup=_aspect_ratio_keyboard())


@router.message(NexusTestStates.aspect_ratio, ~F.text.in_(NEXUS_TEST_EXIT_TEXTS), ~F.text.startswith("/"))
async def nexus_test_aspect_ratio_message(
    message: Message,
    state: FSMContext,
) -> None:
    await message.answer(
        "Выберите соотношение сторон кнопками ниже или нажмите «Отмена».",
        reply_markup=_aspect_ratio_keyboard(),
    )


@router.message(NexusTestStates.image_size, ~F.text.in_(NEXUS_TEST_EXIT_TEXTS), ~F.text.startswith("/"))
async def nexus_test_image_size_message(
    message: Message,
    state: FSMContext,
) -> None:
    await message.answer(
        "Выберите качество кнопками ниже или нажмите «Отмена».",
        reply_markup=_image_size_keyboard(),
    )


@router.callback_query(NexusTestStates.aspect_ratio, F.data.startswith("nexus-test:ratio:"))
async def nexus_test_aspect_ratio(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _state_authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    ratio = str(callback.data or "").split("nexus-test:ratio:", 1)[-1]
    if ratio not in NEXUS_TEST_ASPECT_RATIOS or ratio not in NANO_BANANA_PRO_ASPECT_RATIOS:
        await callback.answer("Неподдерживаемое соотношение", show_alert=True)
        return
    await state.update_data(aspect_ratio=ratio)
    await state.set_state(NexusTestStates.image_size)
    if callback.message:
        await callback.message.answer("Выберите качество:", reply_markup=_image_size_keyboard())
    await callback.answer()


@router.callback_query(NexusTestStates.image_size, F.data.startswith("nexus-test:size:"))
async def nexus_test_image_size(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _state_authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    image_size = str(callback.data or "").split("nexus-test:size:", 1)[-1]
    if image_size not in NEXUS_TEST_IMAGE_SIZES:
        await callback.answer("Неподдерживаемое качество", show_alert=True)
        return
    await state.update_data(image_size=image_size)
    data = await state.get_data()
    references = list(data.get("references") or [])
    prompt = str(data.get("prompt") or "").strip()
    idempotency_key = str(data.get("idempotency_key") or f"ksu-nexus-test:{telegram_id}:{uuid.uuid4()}")
    if not references or not prompt:
        await state.clear()
        await callback.answer("Сессия теста устарела — начните заново", show_alert=True)
        return
    if bool(data.get("running")):
        await callback.answer("Генерация уже поставлена в очередь", show_alert=True)
        return
    await state.update_data(running=True)
    try:
        task = await NexusAdminTaskService.enqueue(
            session,
            telegram_id=int(telegram_id or 0),
            chat_id=int(callback.message.chat.id if callback.message else telegram_id or 0),
            prompt=prompt,
            references=references,
            aspect_ratio=str(data.get("aspect_ratio") or "1:1"),
            image_size=image_size,
            idempotency_key=idempotency_key,
        )
    except Exception:
        await state.update_data(running=False)
        await callback.answer("Не удалось поставить тест в очередь", show_alert=True)
        raise
    await state.clear()
    if callback.message:
        await callback.message.answer(
            f"🧪 Тест поставлен в очередь · {task.id}\n"
            "Результат придёт сюда отдельным сообщением.",
            reply_markup=quick_menu(is_admin=True),
        )
    await callback.answer("Поставлено в очередь")
