from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

router = Router(name="admin-web-retired")


def disable_web_admin_button(admin_module: Any) -> None:
    """Remove the retired web-admin entry from Telegram admin keyboards.

    The underlying Telegram admin router remains the operator surface. This small
    adapter lets us retire the static web admin without rewriting the legacy
    Telegram admin module in the same change.
    """

    original: Callable[[], InlineKeyboardMarkup] = admin_module._main_keyboard

    def filtered_keyboard() -> InlineKeyboardMarkup:
        markup = original()
        markup.inline_keyboard = [
            row
            for row in markup.inline_keyboard
            if all(getattr(button, "callback_data", None) != "admin:web" for button in row)
        ]
        return markup

    admin_module._main_keyboard = filtered_keyboard


@router.callback_query(F.data == "admin:web")
async def admin_web_removed(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "🌐 Web-админка отключена. Используйте Telegram admin menu: /admin."
        )
    await callback.answer("Web-админка удалена", show_alert=True)
