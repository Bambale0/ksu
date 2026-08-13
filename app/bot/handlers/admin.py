from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import back_menu
from app.core.config import settings
from app.db.models import AdminAccount
from app.services.users import UserService

router = Router(name="admin-launch")


@router.message(Command("admin"))
async def admin_console(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user = await UserService.get_or_create(session, message.from_user)
    admin = await session.scalar(
        select(AdminAccount).where(
            AdminAccount.user_id == user.id,
            AdminAccount.is_active.is_(True),
        )
    )
    if admin is None:
        await message.answer(
            "Админ-панель недоступна для этого аккаунта.",
            reply_markup=back_menu(),
        )
        return
    if not settings.public_base_url:
        await message.answer(
            "Админ-панель не настроена: PUBLIC_BASE_URL отсутствует.",
            reply_markup=back_menu(),
        )
        return
    url = f"{settings.public_base_url.rstrip('/')}/admin-app/"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛡 Открыть админ-панель",
                    web_app=WebAppInfo(url=url),
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:main")],
        ]
    )
    await message.answer(
        "Привилегированный доступ. В панели потребуется отдельная admin-сессия и MFA.",
        reply_markup=keyboard,
    )
