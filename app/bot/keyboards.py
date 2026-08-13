from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import settings

BACK_TEXT = "⬅️ Назад"
PRIMARY_PAYMENT_TEXT = "💳 Оплата картой · USD / EUR / RUB / СБП"


def _mini_app_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/mini-app/"


def _create_button() -> InlineKeyboardButton:
    if settings.public_base_url:
        return InlineKeyboardButton(
            text="✨ Создать контент",
            web_app=WebAppInfo(url=_mini_app_url()),
        )
    return InlineKeyboardButton(text="✨ Создать контент", callback_data="create")


def back_menu(callback_data: str = "nav:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BACK_TEXT, callback_data=callback_data)]]
    )


def balance_menu() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if settings.public_base_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=PRIMARY_PAYMENT_TEXT,
                    web_app=WebAppInfo(url=_mini_app_url()),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=BACK_TEXT, callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onboarding_menu() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    links: list[InlineKeyboardButton] = []
    if settings.onboarding_rules_url.startswith("https://"):
        links.append(InlineKeyboardButton(text="Правила", url=settings.onboarding_rules_url))
    if settings.onboarding_privacy_url.startswith("https://"):
        links.append(InlineKeyboardButton(text="Конфиденциальность", url=settings.onboarding_privacy_url))
    if links:
        rows.append(links)
    rows.append([InlineKeyboardButton(text="🚀 Начать", callback_data="onboarding_complete")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_create_button()],
            [InlineKeyboardButton(text="🌐 Лента", callback_data="feed:open")],
            [
                InlineKeyboardButton(text="💎 Баланс", callback_data="balance"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            ],
            [InlineKeyboardButton(text="🤝 Партнёрская программа", callback_data="referrals")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")],
        ]
    )