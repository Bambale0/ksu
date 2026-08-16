from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.core.config import settings

BACK_TEXT = "⬅️ Назад"
PRIMARY_PAYMENT_TEXT = "💳 Оплата картой · USD / EUR / RUB / СБП"
QUICK_MENU_TEXT = "🏠 Меню"
QUICK_SUPPORT_TEXT = "🆘 Поддержка"


def _mini_app_url(route: str | None = None) -> str:
    base = f"{settings.public_base_url.rstrip('/')}/mini-app/"
    if not route:
        return base
    return f"{base}?route={route}"


def _batch_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/mini-app/batch.html"


def _prompt_tool_url(mode: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/mini-app/prompt-tools.html?mode={mode}"


def _route_button(
    *,
    text: str,
    route: str,
    fallback_callback: str,
) -> InlineKeyboardButton:
    if settings.public_base_url:
        return InlineKeyboardButton(
            text=text,
            web_app=WebAppInfo(url=_mini_app_url(route)),
        )
    return InlineKeyboardButton(text=text, callback_data=fallback_callback)


def _batch_button() -> InlineKeyboardButton:
    if settings.public_base_url:
        return InlineKeyboardButton(
            text="🗂 Пакетная обработка",
            web_app=WebAppInfo(url=_batch_url()),
        )
    return InlineKeyboardButton(text="🗂 Пакетная обработка", callback_data="create")


def quick_menu() -> ReplyKeyboardMarkup:
    """Persistent two-button Telegram chrome requested for everyday navigation."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=QUICK_MENU_TEXT),
                KeyboardButton(text=QUICK_SUPPORT_TEXT),
            ]
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="ROXY · выбери действие",
    )


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
                    web_app=WebAppInfo(url=_mini_app_url("wallet")),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text=BACK_TEXT, callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def prompt_tools_menu() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if settings.public_base_url:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        text="🖼 Промпт по фото",
                        web_app=WebAppInfo(url=_prompt_tool_url("image")),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✨ Улучшить промпт",
                        web_app=WebAppInfo(url=_prompt_tool_url("prompt")),
                    )
                ],
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
    """Minimal Telegram launcher: all product navigation lives inside the Mini App."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _route_button(
                    text="🚀 Открыть ROXY",
                    route="home",
                    fallback_callback="nav:main",
                )
            ]
        ]
    )