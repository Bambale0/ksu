from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import settings

BACK_TEXT = "⬅️ Назад"
PRIMARY_PAYMENT_TEXT = "💳 Оплата картой · USD / EUR / RUB / СБП"


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


def _create_button() -> InlineKeyboardButton:
    return _route_button(
        text="✨ Создать",
        route="create",
        fallback_callback="create",
    )


def _batch_button() -> InlineKeyboardButton:
    if settings.public_base_url:
        return InlineKeyboardButton(
            text="🗂 Пакетная обработка",
            web_app=WebAppInfo(url=_batch_url()),
        )
    return InlineKeyboardButton(text="🗂 Пакетная обработка", callback_data="create")


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
                    web_app=WebAppInfo(url=_mini_app_url("profile")),
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
    """Customer-approved ROXY launcher: product work happens inside the Mini App."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _route_button(
                    text="🏠 Главная",
                    route="home",
                    fallback_callback="nav:main",
                )
            ],
            [
                _route_button(
                    text="▦ Каталог",
                    route="catalog",
                    fallback_callback="feed:open",
                )
            ],
            [_create_button()],
            [
                _route_button(
                    text="≡ История",
                    route="history",
                    fallback_callback="nav:main",
                )
            ],
            [
                _route_button(
                    text="👤 Профиль",
                    route="profile",
                    fallback_callback="profile",
                )
            ],
        ]
    )
