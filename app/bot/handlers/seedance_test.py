from __future__ import annotations

import json
import uuid
from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.nexus_test import (
    NEXUS_TEST_EXIT_TEXTS,
    NexusTestStates,
    _is_admin,
    _references_keyboard,
)
from app.bot.keyboards import QUICK_TEST_TEXT, quick_menu
from app.core.config import settings
from app.providers.nexus import NANO_BANANA_PRO_MAX_REFERENCES
from app.providers.neironych_video import NeironychProviderError, NeironychVideoClient, SEEDANCE_TEST_MODELS
from app.services.seedance_admin_tasks import SeedanceAdminTaskService

router = Router(name="seedance-admin-test")


class SeedanceTestStates(StatesGroup):
    prompt = State()
    params = State()


def _model_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🍌 Nano Banana Pro",
                    callback_data="nexus-test:model:nano-banana-pro",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎬 Seedance 2",
                    callback_data="nexus-test:model:seedance-2.0",
                ),
                InlineKeyboardButton(
                    text="🎬 Seedance 2.5",
                    callback_data="nexus-test:model:seedance-2.5",
                ),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")],
        ]
    )


def _params_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Запустить с базовыми параметрами",
                    callback_data="seedance-test:params:default",
                )
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")],
        ]
    )


async def _authorized(
    state: FSMContext,
    session: AsyncSession,
    telegram_id: int | None,
) -> bool:
    if telegram_id is None:
        return False
    data = await state.get_data()
    owner = int(data.get("admin_telegram_id") or 0)
    if owner and owner != telegram_id:
        return False
    return await _is_admin(session, telegram_id)


async def _deny_message(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Тестовый режим доступен только администраторам.")


async def _enqueue(
    *,
    callback_or_message: CallbackQuery | Message,
    state: FSMContext,
    session: AsyncSession,
    extra_payload: dict,
) -> None:
    user = callback_or_message.from_user
    telegram_id = user.id if user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer("Нет доступа", show_alert=True)
        else:
            await callback_or_message.answer("Нет доступа")
        return

    data = await state.get_data()
    model_name = str(data.get("model_name") or "")
    prompt = str(data.get("prompt") or "").strip()
    if model_name not in SEEDANCE_TEST_MODELS or not prompt:
        await state.clear()
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer("Состояние теста устарело", show_alert=True)
        else:
            await callback_or_message.answer("Состояние теста устарело")
        return

    payload = dict(extra_payload)
    # Trusted selections win over raw JSON. Other keys intentionally remain
    # untouched: this is the full provider-lab escape hatch for newly added
    # Seedance parameters.
    payload["model"] = model_name
    payload["prompt"] = prompt
    chat = callback_or_message.message.chat if isinstance(callback_or_message, CallbackQuery) and callback_or_message.message else getattr(callback_or_message, "chat", None)
    if chat is None:
        await state.clear()
        return

    task = await SeedanceAdminTaskService.enqueue(
        session,
        telegram_id=int(telegram_id or 0),
        chat_id=chat.id,
        model_name=model_name,
        request_payload=payload,
        idempotency_key=str(data.get("idempotency_key") or ""),
    )
    await session.commit()
    await state.clear()

    text = (
        f"🧪 {model_name}: задача поставлена в очередь.\n"
        f"Локальная задача: {task.id}\n"
        "ROX не списываются; расходуется только баланс тестового API."
    )
    if isinstance(callback_or_message, CallbackQuery):
        if callback_or_message.message:
            await callback_or_message.message.answer(text, reply_markup=quick_menu(is_admin=True))
        await callback_or_message.answer("Запущено")
    else:
        await callback_or_message.answer(text, reply_markup=quick_menu(is_admin=True))


@router.message(F.text == QUICK_TEST_TEXT)
async def admin_test_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not await _is_admin(session, telegram_id):
        await _deny_message(message, state)
        return
    await state.clear()
    await message.answer(
        "🧪 Тест моделей\n\nВыберите модель. Тесты не списывают ROX.",
        reply_markup=_model_keyboard(),
    )


@router.callback_query(F.data == "nexus-test:model:nano-banana-pro")
async def start_nano_banana_test(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _is_admin(session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not settings.nexus_api_key.strip():
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "NexusAPI пока не настроен: добавьте NEXUS_API_KEY.",
                reply_markup=quick_menu(is_admin=True),
            )
        await callback.answer()
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
    if callback.message:
        await callback.message.answer(
            "🧪 Nano Banana Pro · NexusAPI\n\n"
            f"Пришлите от 1 до {NANO_BANANA_PRO_MAX_REFERENCES} фото-референсов "
            "по одному сообщению. Когда закончите, нажмите «Продолжить».\n\n"
            "Тестовый режим не списывает ROX.",
            reply_markup=_references_keyboard(0),
        )
    await callback.answer()


@router.callback_query(F.data.in_({
    "nexus-test:model:seedance-2",
    "nexus-test:model:seedance-2.5",
}))
async def start_seedance_test(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _is_admin(session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    if not settings.neironych_api_key.strip():
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "Seedance test API пока не настроен: добавьте NEIRONYCH_API_KEY.",
                reply_markup=quick_menu(is_admin=True),
            )
        await callback.answer()
        return

    model_name = str(callback.data or "").rsplit(":", 1)[-1]
    if model_name not in SEEDANCE_TEST_MODELS:
        await callback.answer("Неизвестная модель", show_alert=True)
        return
    await state.set_state(SeedanceTestStates.prompt)
    await state.set_data(
        {
            "model_name": model_name,
            "idempotency_key": f"ksu-seedance-test:{telegram_id}:{uuid.uuid4()}",
            "admin_telegram_id": telegram_id,
        }
    )
    if callback.message:
        await callback.message.answer(
            f"🎬 {model_name}\n\nВведите промпт.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")]
                ]
            ),
        )
    await callback.answer()


@router.message(
    SeedanceTestStates.prompt,
    ~F.text.in_(NEXUS_TEST_EXIT_TEXTS),
    ~F.text.startswith("/"),
)
async def seedance_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not await _authorized(state, session, telegram_id):
        await _deny_message(message, state)
        return
    prompt = str(message.text or "").strip()
    if not prompt:
        await message.answer("Промпт не может быть пустым.")
        return
    await state.update_data(prompt=prompt)
    await state.set_state(SeedanceTestStates.params)
    await message.answer(
        "Теперь можно либо запустить базовый запрос, либо прислать JSON-объект "
        "с любыми дополнительными параметрами из актуальной документации API. "
        "Фото, видео, аудио или document можно отправить прямо сюда: бот загрузит "
        "файл в /v1/media/uploads и вернёт URL для JSON.\n\n"
        "Пример: {\"duration\": 8, \"aspect_ratio\": \"9:16\", "
        "\"resolution\": \"720p\"}\n\n"
        "Поля model и prompt задаются ботом и из JSON не переопределяются.",
        reply_markup=_params_keyboard(),
    )


@router.callback_query(F.data == "seedance-test:params:default")
async def seedance_default_params(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _enqueue(
        callback_or_message=callback,
        state=state,
        session=session,
        extra_payload={
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "duration": 5,
            "generate_audio": False,
            "return_last_frame": False,
            "output_format": "mp4",
            "web_search": False,
        },
    )


@router.message(
    SeedanceTestStates.params,
    F.photo | F.video | F.audio | F.document,
)
async def seedance_upload_media(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not await _authorized(state, session, telegram_id):
        await _deny_message(message, state)
        return

    file_id = ""
    filename = "media.bin"
    mime_type = "application/octet-stream"
    file_size = 0
    if message.photo:
        item = message.photo[-1]
        file_id = item.file_id
        filename = f"{item.file_unique_id}.jpg"
        mime_type = "image/jpeg"
        file_size = int(item.file_size or 0)
    elif message.video:
        item = message.video
        file_id = item.file_id
        filename = item.file_name or f"{item.file_unique_id}.mp4"
        mime_type = item.mime_type or "video/mp4"
        file_size = int(item.file_size or 0)
    elif message.audio:
        item = message.audio
        file_id = item.file_id
        filename = item.file_name or f"{item.file_unique_id}.mp3"
        mime_type = item.mime_type or "audio/mpeg"
        file_size = int(item.file_size or 0)
    elif message.document:
        item = message.document
        file_id = item.file_id
        filename = item.file_name or f"{item.file_unique_id}.bin"
        mime_type = item.mime_type or "application/octet-stream"
        file_size = int(item.file_size or 0)

    if not file_id:
        await message.answer("Не удалось определить Telegram file_id.")
        return
    if file_size and file_size > settings.neironych_test_max_video_bytes:
        await message.answer("Файл больше лимита тестового контура.")
        return

    buffer = BytesIO()
    try:
        await message.bot.download(file_id, destination=buffer)
        content = buffer.getvalue()
        if len(content) > settings.neironych_test_max_video_bytes:
            await message.answer("Файл больше лимита тестового контура.")
            return
        client = NeironychVideoClient(
            settings.neironych_api_key,
            settings.neironych_api_base_url,
        )
        try:
            url = await client.upload_media(
                content=content,
                filename=filename,
                mime_type=mime_type,
            )
        finally:
            await client.aclose()
    except NeironychProviderError as exc:
        await message.answer(f"Не удалось загрузить media: {str(exc)[:800]}")
        return

    await message.answer(
        "✅ Media загружено. Вставьте этот URL в нужное поле JSON "
        "(first_frame_url / last_frame_url / reference_*_urls):\n"
        f"{url}"
    )


@router.message(
    SeedanceTestStates.params,
    ~F.text.in_(NEXUS_TEST_EXIT_TEXTS),
    ~F.text.startswith("/"),
)
async def seedance_raw_params(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not await _authorized(state, session, telegram_id):
        await _deny_message(message, state)
        return
    raw = str(message.text or "").strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        await message.answer(f"JSON не разобран: {exc.msg} (позиция {exc.pos}).")
        return
    if not isinstance(value, dict):
        await message.answer("Нужен JSON-объект, а не массив или строка.")
        return
    if len(raw.encode("utf-8")) > 64 * 1024:
        await message.answer("JSON слишком большой. Лимит тестового payload — 64 КБ.")
        return
    await _enqueue(
        callback_or_message=message,
        state=state,
        session=session,
        extra_payload=value,
    )
