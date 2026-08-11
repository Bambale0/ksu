from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✨ Создать контент", callback_data="create")],
            [
                InlineKeyboardButton(text="💎 Баланс ROX", callback_data="balance"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            ],
            [InlineKeyboardButton(text="🤝 Партнёрская программа", callback_data="referrals")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
        ]
    )
