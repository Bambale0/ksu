from urllib.parse import urlencode

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.core.config import settings

BACK_TEXT = "⬅️ Назад"
PRIMARY_PAYMENT_TEXT = "💳 Оплата картой"
OPEN_APP_TEXT = "🚀 Открыть ROXY"
QUICK_MENU_TEXT = "🏠 Меню"
QUICK_PROMPT_TEXT = "✨ Описание для фото"
QUICK_VIDEO_PROMPT_TEXT = "🎬 Описание для видео"
QUICK_SUPPORT_TEXT = "🆘 Поддержка"


def _ref_code_from_start_payload(start_payload: str) -> str | None:
    payload = start_payload.strip()
    if payload.casefold().startswith("ref_"):
        code = payload[4:].strip()
        return code or None
    return None


def _mini_app_url(route: str | None = None, *, start_payload: str | None = None) -> str:
    base = f"{settings.public_base_url.rstrip('/')}/mini-app/"
    query: dict[str, str] = {}
    if route:
        query["route"] = route
    start_payload = str(start_payload or "").strip()
    if start_payload:
        # Telegram exposes Main Mini App payload as start_param/startapp.
        # Keep the product-owned start_payload for the Next app and add the
        # Banano-compatible aliases that make referral opening deterministic.
        query["start_payload"] = start_payload
        query["startapp"] = start_payload
        if ref_code := _ref_code_from_start_payload(start_payload):
            query["ref"] = ref_code.upper()
    if not query:
        return base
    return f"{base}?{urlencode(query)}"


def _batch_url() -> str:
    return f"{settings.public_base_url.rstrip('/')}/mini-app/batch.html"


def _prompt_tool_url(mode: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/mini-app/prompt-tools.html?mode={mode}"


def _open_app_inline_button(*, route: str = "catalog", start_payload: str | None = None) -> InlineKeyboardButton:
    if not settings.public_base_url:
        return InlineKeyboardButton(text=OPEN_APP_TEXT, callback_data="app:unavailable")
    return InlineKeyboardButton(
        text=OPEN_APP_TEXT,
        web_app=WebAppInfo(url=_mini_app_url(route, start_payload=start_payload)),
    )


def app_launcher_menu(
    *,
    route: str = "catalog",
    start_payload: str | None = None,
) -> InlineKeyboardMarkup:
    """Inline app launcher: only the ROXY Mini App button under the message."""
    primary = OPEN_APP_TEXT  # contract: text="🚀 Открыть ROXY"
    del primary
    return InlineKeyboardMarkup(
        inline_keyboard=[[_open_app_inline_button(route=route, start_payload=start_payload)]]
    )


def feed_work_menu(start_payload: str) -> InlineKeyboardMarkup:
    """Open the exact shared feed publication inside the Mini App."""

    payload = str(start_payload or "").strip()
    if not settings.public_base_url or not payload:
        button = InlineKeyboardButton(text="Открыть работу в ROXY", callback_data="app:unavailable")
    else:
        button = InlineKeyboardButton(
            text="Открыть работу в ROXY",
            web_app=WebAppInfo(url=_mini_app_url("feed", start_payload=payload)),
        )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])


def app_reply_menu() -> ReplyKeyboardMarkup:
    """Persistent Telegram bottom keyboard: only menu and support."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=QUICK_MENU_TEXT), KeyboardButton(text=QUICK_SUPPORT_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Меню или поддержка",
    )


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
    """Compatibility keyboard for launcher and support shortcuts."""
    return app_reply_menu()


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
                        text="✨ Описание по фото или идее",
                        web_app=WebAppInfo(url=_prompt_tool_url("image")),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎬 Описание по видео",
                        web_app=WebAppInfo(url=_prompt_tool_url("video")),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🎞 Сценарий для видео",
                        web_app=WebAppInfo(url=_prompt_tool_url("seedance")),
                    )
                ],
            ]
        )
    rows.append([InlineKeyboardButton(text=BACK_TEXT, callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onboarding_menu() -> InlineKeyboardMarkup:
    """Legacy text-bot onboarding keyboard; app onboarding is authoritative."""
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


def main_menu_with_start_payload(start_payload: str | None = None) -> InlineKeyboardMarkup:
    """Open the Mini App catalog while preserving a Telegram start payload."""
    return app_launcher_menu(route="catalog", start_payload=start_payload)


def main_menu() -> InlineKeyboardMarkup:
    """Compatibility alias for older imports; customer UX opens the Mini App catalog."""
    return app_launcher_menu(route="catalog")
