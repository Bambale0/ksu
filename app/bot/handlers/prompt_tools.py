from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import prompt_tools_menu
from app.services.users import UserService

router = Router(name="prompt-tools")


async def _open(message: Message, session: AsyncSession) -> None:
    await UserService.get_or_create(session, message.from_user)
    await message.answer(
        "🧠 <b>AI-инструменты</b>\n\n"
        "🖼 <b>Промпт по фото</b> — композиция, стиль, свет, цвета, ракурс и детали.\n"
        "✨ <b>Улучшить промпт</b> — цельный RU/EN промпт из идеи и, при желании, референса.\n\n"
        "Стоимость показывается до запуска и берётся с сервера.",
        reply_markup=prompt_tools_menu(),
    )


@router.message(Command("prompt_tools"))
@router.message(Command("photo_prompt"))
@router.message(Command("prompt"))
async def prompt_tools_command(message: Message, session: AsyncSession) -> None:
    await _open(message, session)


@router.callback_query(F.data == "prompt-tools:open")
async def prompt_tools_open(callback: CallbackQuery, session: AsyncSession) -> None:
    await UserService.get_or_create(session, callback.from_user)
    await callback.answer()
    if isinstance(callback.message, Message):
        await _open(callback.message, session)
