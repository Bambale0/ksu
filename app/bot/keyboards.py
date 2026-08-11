from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import settings


def _create_button() -> InlineKeyboardButton:
    if settings.public_base_url:
        return InlineKeyboardButton(
            text="✨ Создать контент",
            web_app=WebAppInfo(url=f"{settings.public_base_url.rstrip('/')}/mini-app/"),
        )
    return InlineKeyboardButton(text="✨ Создать контент", callback_data="create")


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_create_button()],
            [
                InlineKeyboardButton(text="💎 Баланс", callback_data="balance"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            ],
            [InlineKeyboardButton(text="🤝 Партнёрская программа", callback_data="referrals")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
        ]
    )
