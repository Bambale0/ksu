from __future__ import annotations

import json
import uuid
from io import BytesIO
from typing import Any

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
from app.providers.neironych_video import (
    NeironychProviderError,
    NeironychVideoClient,
    SEEDANCE_TEST_MODELS,
    enabled_seedance_test_models,
)
from app.services.neironych_video_contracts import (
    NeironychVideoContractError,
    normalize_neironych_video_input,
)
from app.services.seedance_admin_tasks import SeedanceAdminTaskService
from app.services.seedance_test_wizard import (
    SeedanceWizardError,
    build_seedance_payload,
    get_seedance_test_spec,
    reference_counts,
)

router = Router(name="seedance-admin-test")


class SeedanceTestStates(StatesGroup):
    mode = State()
    prompt = State()
    resolution = State()
    duration = State()
    aspect_ratio = State()
    references = State()
    review = State()
    params = State()  # Expert raw-JSON escape hatch.


def _model_keyboard(
    enabled_seedance_models: tuple[str, ...] = SEEDANCE_TEST_MODELS,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🍌 Nano Banana Pro",
                callback_data="nexus-test:model:nano-banana-pro",
            )
        ]
    ]
    seedance_buttons: list[InlineKeyboardButton] = []
    if "seedance-2.0" in enabled_seedance_models:
        seedance_buttons.append(
            InlineKeyboardButton(
                text="🎬 Seedance 2",
                callback_data="nexus-test:model:seedance-2.0",
            )
        )
    if "seedance-2.5" in enabled_seedance_models:
        seedance_buttons.append(
            InlineKeyboardButton(
                text="🎬 Seedance 2.5",
                callback_data="nexus-test:model:seedance-2.5",
            )
        )
    if seedance_buttons:
        rows.append(seedance_buttons)
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _provider_enabled_seedance_models() -> tuple[str, ...]:
    client = NeironychVideoClient(
        settings.neironych_api_key,
        settings.neironych_api_base_url,
    )
    try:
        available = await client.list_models()
    except NeironychProviderError:
        raise
    except Exception as exc:
        raise NeironychProviderError(
            "Не удалось получить список моделей Seedance у провайдера."
        ) from exc
    finally:
        await client.aclose()
    return enabled_seedance_test_models(available)


def _seedance_unavailable_text(
    model_name: str,
    enabled_seedance_models: tuple[str, ...],
) -> str:
    available = ", ".join(enabled_seedance_models) or "нет доступных Seedance-моделей"
    return (
        f"Модель {model_name} сейчас не включена у провайдера. "
        f"Доступно: {available}"
    )


def _mode_keyboard(model_name: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📝 Текст → видео", callback_data="seedance-test:mode:text")],
        [
            InlineKeyboardButton(
                text="🧩 Мультиреференсы",
                callback_data="seedance-test:mode:reference",
            )
        ],
        [
            InlineKeyboardButton(
                text="🖼 Первый / последний кадр",
                callback_data="seedance-test:mode:frame",
            )
        ],
    ]
    if get_seedance_test_spec(model_name).supports_edit:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎞 Редактирование видео",
                    callback_data="seedance-test:mode:edit",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🧰 Raw JSON · эксперт",
                callback_data="seedance-test:mode:raw",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _resolution_keyboard(model_name: str) -> InlineKeyboardMarkup:
    spec = get_seedance_test_spec(model_name)
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    for value in spec.resolutions:
        current.append(
            InlineKeyboardButton(
                text=value,
                callback_data=f"seedance-test:resolution:{value}",
            )
        )
        if len(current) == 3:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _duration_keyboard(model_name: str) -> InlineKeyboardMarkup:
    spec = get_seedance_test_spec(model_name)
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    for value in range(spec.min_duration, spec.max_duration + 1):
        current.append(
            InlineKeyboardButton(
                text=f"{value}с",
                callback_data=f"seedance-test:duration:{value}",
            )
        )
        if len(current) == 5:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _aspect_ratio_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1:1", callback_data="seedance-test:ratio:1:1"),
                InlineKeyboardButton(text="16:9", callback_data="seedance-test:ratio:16:9"),
                InlineKeyboardButton(text="9:16", callback_data="seedance-test:ratio:9:16"),
            ],
            [
                InlineKeyboardButton(text="4:3", callback_data="seedance-test:ratio:4:3"),
                InlineKeyboardButton(text="3:4", callback_data="seedance-test:ratio:3:4"),
                InlineKeyboardButton(text="21:9", callback_data="seedance-test:ratio:21:9"),
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")],
        ]
    )


def _seedance_default_payload() -> dict[str, object]:
    return {
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "duration": 5,
    }


def _reference_keyboard(data: dict[str, Any]) -> InlineKeyboardMarkup:
    model_name = str(data.get("model_name") or "")
    mode = str(data.get("mode") or "")
    spec = get_seedance_test_spec(model_name)
    images, videos, audios = reference_counts(data)
    rows: list[list[InlineKeyboardButton]] = []
    if mode == "frame":
        frame_count = int(bool(data.get("start_image"))) + int(bool(data.get("end_image")))
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Готово · кадров {frame_count}/2",
                    callback_data="seedance-test:refs:done",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Готово · 📷{images} 🎥{videos} 🎵{audios}",
                    callback_data="seedance-test:refs:done",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"Лимиты: {spec.max_image_refs}/{spec.max_video_refs}/"
                        f"{spec.max_audio_refs} · Σ{spec.max_total_refs}"
                    ),
                    callback_data="seedance-test:refs:limits",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🗑 Очистить",
                callback_data="seedance-test:refs:clear",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _review_keyboard(data: dict[str, Any]) -> InlineKeyboardMarkup:
    mode = str(data.get("mode") or "")
    rows = [
        [InlineKeyboardButton(text="🚀 Запустить", callback_data="seedance-test:launch")],
        [
            InlineKeyboardButton(
                text="📝 Изменить промпт",
                callback_data="seedance-test:review:prompt",
            ),
            InlineKeyboardButton(
                text="🎛 Параметры",
                callback_data="seedance-test:review:params",
            ),
        ],
    ]
    if mode in {"reference", "frame", "edit"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📎 Референсы",
                    callback_data="seedance-test:review:refs",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="nexus-test:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _review_text(data: dict[str, Any], payload: dict[str, Any]) -> str:
    images, videos, audios = reference_counts(data)
    mode = str(data.get("mode") or "")
    lines = [
        "🧪 Seedance · проверка перед запуском",
        "",
        f"Модель: {data.get('model_name')}",
        f"Режим: {mode}",
        f"Разрешение: {payload.get('resolution', 'по источнику')}",
        f"Длительность: {payload.get('duration', 'по источнику')} сек"
        if "duration" in payload
        else "Длительность: по исходному видео",
        f"Соотношение: {payload.get('aspect_ratio', 'по источнику')}",
    ]
    if mode == "frame":
        lines.append(
            "Кадры: "
            + ("старт ✅" if data.get("start_image") else "старт —")
            + " · "
            + ("финиш ✅" if data.get("end_image") else "финиш —")
        )
    elif mode in {"reference", "edit"}:
        lines.append(f"Референсы: 📷 {images} · 🎥 {videos} · 🎵 {audios}")
    lines.extend(
        [
            "",
            "Промпт проверен локально; запрещённые legacy-поля не уйдут провайдеру.",
            "ROX не списываются — расходуется тестовый API-баланс.",
        ]
    )
    return "\n".join(lines)


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

    candidate = dict(extra_payload)
    candidate["prompt"] = prompt
    try:
        payload = normalize_neironych_video_input(model_name, candidate)
    except NeironychVideoContractError as exc:
        text = f"Параметры Seedance невалидны: {str(exc)[:1200]}"
        if isinstance(callback_or_message, CallbackQuery):
            if callback_or_message.message:
                await callback_or_message.message.answer(text)
            await callback_or_message.answer("Проверьте параметры", show_alert=True)
        else:
            await callback_or_message.answer(text)
        return
    payload["model"] = model_name

    try:
        enabled_seedance_models = await _provider_enabled_seedance_models()
    except NeironychProviderError:
        text = (
            "Не удалось проверить доступность Seedance у провайдера. "
            "Задача не поставлена в очередь — попробуйте ещё раз."
        )
        if isinstance(callback_or_message, CallbackQuery):
            if callback_or_message.message:
                await callback_or_message.message.answer(text)
            await callback_or_message.answer("Не удалось проверить модель", show_alert=True)
        else:
            await callback_or_message.answer(text)
        return
    if model_name not in enabled_seedance_models:
        text = _seedance_unavailable_text(model_name, enabled_seedance_models)
        if isinstance(callback_or_message, CallbackQuery):
            if callback_or_message.message:
                await callback_or_message.message.answer(
                    text,
                    reply_markup=_model_keyboard(enabled_seedance_models),
                )
            await callback_or_message.answer("Модель сейчас недоступна", show_alert=True)
        else:
            await callback_or_message.answer(
                text,
                reply_markup=_model_keyboard(enabled_seedance_models),
            )
        return

    chat = (
        callback_or_message.message.chat
        if isinstance(callback_or_message, CallbackQuery) and callback_or_message.message
        else getattr(callback_or_message, "chat", None)
    )
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


async def _show_review(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    try:
        payload = build_seedance_payload(data)
    except SeedanceWizardError as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await state.set_state(SeedanceTestStates.review)
    await state.update_data(wizard_payload=payload)
    if callback.message:
        await callback.message.answer(
            _review_text(data, payload),
            reply_markup=_review_keyboard(data),
        )
    await callback.answer()


def _message_media(message: Message) -> tuple[str, str, str, int, str] | None:
    if message.photo:
        item = message.photo[-1]
        return (
            "image",
            item.file_id,
            f"{item.file_unique_id}.jpg",
            int(item.file_size or 0),
            "image/jpeg",
        )
    if message.video:
        item = message.video
        return (
            "video",
            item.file_id,
            item.file_name or f"{item.file_unique_id}.mp4",
            int(item.file_size or 0),
            item.mime_type or "video/mp4",
        )
    if message.audio:
        item = message.audio
        return (
            "audio",
            item.file_id,
            item.file_name or f"{item.file_unique_id}.mp3",
            int(item.file_size or 0),
            item.mime_type or "audio/mpeg",
        )
    if message.voice:
        item = message.voice
        return (
            "audio",
            item.file_id,
            f"{item.file_unique_id}.ogg",
            int(item.file_size or 0),
            item.mime_type or "audio/ogg",
        )
    if message.document:
        item = message.document
        mime = str(item.mime_type or "application/octet-stream").lower()
        kind = (
            "image"
            if mime.startswith("image/")
            else "video"
            if mime.startswith("video/")
            else "audio"
            if mime.startswith("audio/")
            else ""
        )
        if not kind:
            return None
        return (
            kind,
            item.file_id,
            item.file_name or f"{item.file_unique_id}.bin",
            int(item.file_size or 0),
            mime,
        )
    return None


async def _upload_media(
    message: Message,
    *,
    model_name: str,
) -> tuple[str, str] | None:
    media = _message_media(message)
    if media is None:
        await message.answer("Пришлите фото, видео или аудио-файл.")
        return None
    kind, file_id, _filename, file_size, mime_type = media
    if file_size and file_size > settings.neironych_test_max_video_bytes:
        await message.answer("Файл больше лимита тестового контура.")
        return None

    buffer = BytesIO()
    try:
        await message.bot.download(file_id, destination=buffer)
        content = buffer.getvalue()
        if len(content) > settings.neironych_test_max_video_bytes:
            await message.answer("Файл больше лимита тестового контура.")
            return None
        client = NeironychVideoClient(
            settings.neironych_api_key,
            settings.neironych_api_base_url,
        )
        try:
            url = await client.upload_media(
                model=model_name,
                media_type=kind,
                content=content,
                mime_type=mime_type,
            )
        finally:
            await client.aclose()
    except NeironychProviderError as exc:
        await message.answer(f"Не удалось загрузить media: {str(exc)[:800]}")
        return None
    return kind, url


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
    enabled_seedance_models: tuple[str, ...] = ()
    seedance_note = ""
    if settings.neironych_api_key.strip():
        try:
            enabled_seedance_models = await _provider_enabled_seedance_models()
        except NeironychProviderError:
            seedance_note = (
                "\n\n⚠️ Seedance временно скрыт: "
                "не удалось проверить доступные модели у провайдера."
            )
        else:
            if not enabled_seedance_models:
                seedance_note = (
                    "\n\n⚠️ Для текущего тестового контура "
                    "нет включённых моделей Seedance."
                )
    else:
        seedance_note = "\n\n⚠️ Seedance test API не настроен."

    await message.answer(
        "🧪 Тест моделей\n\nВыберите модель. Тесты не списывают ROX."
        + seedance_note,
        reply_markup=_model_keyboard(enabled_seedance_models),
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


@router.callback_query(
    F.data.in_(
        {
            "nexus-test:model:seedance-2.0",
            "nexus-test:model:seedance-2.5",
        }
    )
)
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

    try:
        enabled_seedance_models = await _provider_enabled_seedance_models()
    except NeironychProviderError:
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "Не удалось проверить доступные модели Seedance у провайдера. "
                "Откройте тест моделей ещё раз.",
                reply_markup=quick_menu(is_admin=True),
            )
        await callback.answer("Не удалось проверить модели", show_alert=True)
        return
    if model_name not in enabled_seedance_models:
        await state.clear()
        if callback.message:
            await callback.message.answer(
                _seedance_unavailable_text(model_name, enabled_seedance_models),
                reply_markup=_model_keyboard(enabled_seedance_models),
            )
        await callback.answer("Модель сейчас недоступна", show_alert=True)
        return

    await state.set_state(SeedanceTestStates.mode)
    await state.set_data(
        {
            "model_name": model_name,
            "idempotency_key": f"ksu-seedance-test:{telegram_id}:{uuid.uuid4()}",
            "admin_telegram_id": telegram_id,
            "reference_images": [],
            "reference_videos": [],
            "reference_audios": [],
        }
    )
    if callback.message:
        await callback.message.answer(
            f"🎬 {model_name}\n\nВыберите сценарий теста.",
            reply_markup=_mode_keyboard(model_name),
        )
    await callback.answer()


@router.callback_query(SeedanceTestStates.mode, F.data.startswith("seedance-test:mode:"))
async def seedance_mode(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    mode = str(callback.data or "").rsplit(":", 1)[-1]
    data = await state.get_data()
    spec = get_seedance_test_spec(str(data.get("model_name") or ""))
    if mode == "edit" and not spec.supports_edit:
        await callback.answer("Edit доступен только для Seedance 2.5", show_alert=True)
        return
    if mode not in {"text", "reference", "frame", "edit", "raw"}:
        await callback.answer("Неизвестный режим", show_alert=True)
        return
    await state.update_data(
        mode=mode,
        reference_images=[],
        reference_videos=[],
        reference_audios=[],
        start_image=None,
        end_image=None,
        wizard_payload=None,
    )
    await state.set_state(SeedanceTestStates.prompt)
    if callback.message:
        await callback.message.answer(
            "Введите промпт Seedance.",
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
    if len(prompt.encode("utf-8")) > 40_000:
        await message.answer("Промпт превышает лимит 40 000 байт UTF-8.")
        return
    await state.update_data(prompt=prompt)
    data = await state.get_data()
    if str(data.get("mode") or "") == "raw":
        await state.set_state(SeedanceTestStates.params)
        await message.answer(
            "🧰 Экспертный режим. Пришлите JSON дополнительных параметров. "
            "model и prompt задаются ботом. Известные нелегальные legacy-поля "
            "будут удалены, а контракт Seedance проверен локально.\n\n"
            'Пример: {"duration": 8, "aspect_ratio": "9:16", "resolution": "720p"}'
        )
        return

    await state.set_state(SeedanceTestStates.resolution)
    await message.answer(
        "Выберите разрешение:",
        reply_markup=_resolution_keyboard(str(data.get("model_name") or "")),
    )


@router.callback_query(
    SeedanceTestStates.resolution,
    F.data.startswith("seedance-test:resolution:"),
)
async def seedance_resolution(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    value = str(callback.data or "").rsplit(":", 1)[-1]
    data = await state.get_data()
    spec = get_seedance_test_spec(str(data.get("model_name") or ""))
    if value not in spec.resolutions:
        await callback.answer("Неподдерживаемое разрешение", show_alert=True)
        return
    await state.update_data(resolution=value)
    mode = str(data.get("mode") or "")
    if mode == "edit":
        await state.set_state(SeedanceTestStates.references)
        if callback.message:
            await callback.message.answer(
                "🎞 Edit mode: пришлите исходное видео. Можно также добавить фото/аудио "
                "референсы. Длительность и aspect ratio берутся из исходника.",
                reply_markup=_reference_keyboard(await state.get_data()),
            )
        await callback.answer()
        return
    await state.set_state(SeedanceTestStates.duration)
    if callback.message:
        await callback.message.answer(
            "Выберите длительность:",
            reply_markup=_duration_keyboard(str(data.get("model_name") or "")),
        )
    await callback.answer()


@router.callback_query(
    SeedanceTestStates.duration,
    F.data.startswith("seedance-test:duration:"),
)
async def seedance_duration(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        value = int(str(callback.data or "").rsplit(":", 1)[-1])
    except ValueError:
        await callback.answer("Некорректная длительность", show_alert=True)
        return
    data = await state.get_data()
    spec = get_seedance_test_spec(str(data.get("model_name") or ""))
    if not spec.min_duration <= value <= spec.max_duration:
        await callback.answer("Неподдерживаемая длительность", show_alert=True)
        return
    await state.update_data(duration=value)
    mode = str(data.get("mode") or "")
    if mode == "frame":
        await state.update_data(aspect_ratio="adaptive")
        await state.set_state(SeedanceTestStates.references)
        if callback.message:
            await callback.message.answer(
                "🖼 Frame mode: пришлите стартовое изображение и, при необходимости, "
                "второе изображение как конечный кадр. Aspect ratio = adaptive.",
                reply_markup=_reference_keyboard(await state.get_data()),
            )
        await callback.answer()
        return
    await state.set_state(SeedanceTestStates.aspect_ratio)
    if callback.message:
        await callback.message.answer(
            "Выберите соотношение сторон:",
            reply_markup=_aspect_ratio_keyboard(),
        )
    await callback.answer()


@router.callback_query(
    SeedanceTestStates.aspect_ratio,
    F.data.startswith("seedance-test:ratio:"),
)
async def seedance_aspect_ratio(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    value = str(callback.data or "").split("seedance-test:ratio:", 1)[-1]
    if value not in {"1:1", "16:9", "9:16", "4:3", "3:4", "21:9"}:
        await callback.answer("Неподдерживаемое соотношение", show_alert=True)
        return
    await state.update_data(aspect_ratio=value)
    data = await state.get_data()
    mode = str(data.get("mode") or "")
    if mode == "text":
        await _show_review(callback, state)
        return
    await state.set_state(SeedanceTestStates.references)
    if callback.message:
        spec = get_seedance_test_spec(str(data.get("model_name") or ""))
        await callback.message.answer(
            "📎 Пришлите фото, видео или аудио референсы по одному сообщению.\n"
            f"Лимиты: фото {spec.max_image_refs}, видео {spec.max_video_refs}, "
            f"аудио {spec.max_audio_refs}, суммарно {spec.max_total_refs}.",
            reply_markup=_reference_keyboard(await state.get_data()),
        )
    await callback.answer()


@router.message(
    SeedanceTestStates.references,
    F.photo | F.video | F.audio | F.voice | F.document,
)
async def seedance_reference_media(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not await _authorized(state, session, telegram_id):
        await _deny_message(message, state)
        return
    data = await state.get_data()
    model_name = str(data.get("model_name") or "")
    mode = str(data.get("mode") or "")
    spec = get_seedance_test_spec(model_name)
    media = _message_media(message)
    if media is None:
        await message.answer("Поддерживаются изображения, видео и аудио.")
        return
    kind = media[0]

    if mode == "frame" and kind != "image":
        await message.answer("Frame mode принимает только изображения.")
        return
    if mode == "frame" and data.get("start_image") and data.get("end_image"):
        await message.answer(
            "Уже добавлены стартовый и конечный кадры. Очистите их, чтобы заменить.",
            reply_markup=_reference_keyboard(data),
        )
        return

    images, videos, audios = reference_counts(data)
    total = images + videos + audios
    if mode != "frame":
        limits = {
            "image": spec.max_image_refs,
            "video": spec.max_video_refs,
            "audio": spec.max_audio_refs,
        }
        current = {"image": images, "video": videos, "audio": audios}[kind]
        if current >= limits[kind]:
            await message.answer(
                f"Лимит {kind}: {limits[kind]}.",
                reply_markup=_reference_keyboard(data),
            )
            return
        if total >= spec.max_total_refs:
            await message.answer(
                f"Достигнут суммарный лимит {spec.max_total_refs} референсов.",
                reply_markup=_reference_keyboard(data),
            )
            return

    uploaded = await _upload_media(message, model_name=model_name)
    if uploaded is None:
        return
    kind, url = uploaded

    if mode == "frame":
        if not data.get("start_image"):
            await state.update_data(start_image=url)
            label = "Стартовый кадр добавлен"
        else:
            await state.update_data(end_image=url)
            label = "Конечный кадр добавлен"
    else:
        key = {
            "image": "reference_images",
            "video": "reference_videos",
            "audio": "reference_audios",
        }[kind]
        values = list(data.get(key) or [])
        values.append(url)
        await state.update_data(**{key: values})
        label = {"image": "Фото", "video": "Видео", "audio": "Аудио"}[kind] + " добавлено"

    fresh = await state.get_data()
    await message.answer(label, reply_markup=_reference_keyboard(fresh))


@router.message(
    SeedanceTestStates.references,
    ~F.text.in_(NEXUS_TEST_EXIT_TEXTS),
    ~F.text.startswith("/"),
)
async def seedance_reference_hint(message: Message, state: FSMContext) -> None:
    await message.answer(
        "Пришлите референс как фото/видео/аудио либо используйте кнопки.",
        reply_markup=_reference_keyboard(await state.get_data()),
    )


@router.callback_query(
    SeedanceTestStates.references,
    F.data == "seedance-test:refs:limits",
)
async def seedance_reference_limits(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    spec = get_seedance_test_spec(str(data.get("model_name") or ""))
    await callback.answer(
        f"Фото {spec.max_image_refs}; видео {spec.max_video_refs}; "
        f"аудио {spec.max_audio_refs}; всего {spec.max_total_refs}",
        show_alert=True,
    )


@router.callback_query(
    SeedanceTestStates.references,
    F.data == "seedance-test:refs:clear",
)
async def seedance_clear_references(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.update_data(
        reference_images=[],
        reference_videos=[],
        reference_audios=[],
        start_image=None,
        end_image=None,
    )
    if callback.message:
        await callback.message.edit_reply_markup(
            reply_markup=_reference_keyboard(await state.get_data())
        )
    await callback.answer("Референсы очищены")


@router.callback_query(
    SeedanceTestStates.references,
    F.data == "seedance-test:refs:done",
)
async def seedance_references_done(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    mode = str(data.get("mode") or "")
    images, videos, audios = reference_counts(data)
    if mode == "reference" and not (images or videos or audios):
        await callback.answer("Добавьте хотя бы один референс", show_alert=True)
        return
    if mode == "frame" and not data.get("start_image"):
        await callback.answer("Добавьте стартовый кадр", show_alert=True)
        return
    if mode == "edit" and not videos:
        await callback.answer("Edit требует исходное видео", show_alert=True)
        return
    await _show_review(callback, state)


@router.callback_query(SeedanceTestStates.review, F.data == "seedance-test:launch")
async def seedance_launch(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    try:
        payload = build_seedance_payload(data)
    except SeedanceWizardError as exc:
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await _enqueue(
        callback_or_message=callback,
        state=state,
        session=session,
        extra_payload=payload,
    )


@router.callback_query(
    SeedanceTestStates.review,
    F.data == "seedance-test:review:prompt",
)
async def seedance_review_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.set_state(SeedanceTestStates.prompt)
    if callback.message:
        await callback.message.answer("Введите новый промпт.")
    await callback.answer()


@router.callback_query(
    SeedanceTestStates.review,
    F.data == "seedance-test:review:params",
)
async def seedance_review_params(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    await state.set_state(SeedanceTestStates.resolution)
    if callback.message:
        await callback.message.answer(
            "Выберите разрешение:",
            reply_markup=_resolution_keyboard(str(data.get("model_name") or "")),
        )
    await callback.answer()


@router.callback_query(
    SeedanceTestStates.review,
    F.data == "seedance-test:review:refs",
)
async def seedance_review_refs(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    telegram_id = callback.from_user.id if callback.from_user else None
    if not await _authorized(state, session, telegram_id):
        await state.clear()
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    if str(data.get("mode") or "") == "text":
        await callback.answer("В текстовом режиме референсов нет", show_alert=True)
        return
    await state.set_state(SeedanceTestStates.references)
    if callback.message:
        await callback.message.answer(
            "Добавьте/очистите референсы и нажмите «Готово».",
            reply_markup=_reference_keyboard(data),
        )
    await callback.answer()


@router.callback_query(F.data == "seedance-test:params:default")
async def seedance_default_params(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    # Kept for backwards-compatible stale keyboards/messages. New sessions use
    # the full wizard, but old Telegram messages can still be tapped safely.
    await _enqueue(
        callback_or_message=callback,
        state=state,
        session=session,
        extra_payload=_seedance_default_payload(),
    )


@router.message(
    SeedanceTestStates.params,
    F.photo | F.video | F.audio | F.voice | F.document,
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
    data = await state.get_data()
    model_name = str(data.get("model_name") or "")
    uploaded = await _upload_media(message, model_name=model_name)
    if uploaded is None:
        return
    kind, url = uploaded
    await message.answer(
        f"✅ {kind} загружено. URL для Raw JSON:\n{url}"
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
