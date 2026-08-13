from __future__ import annotations

import uuid

from app.bot.handlers.feed import _keyboard


def _card() -> dict[str, object]:
    return {
        "id": str(uuid.uuid4()),
        "author_referral_code": "999999999999",
        "liked_by_me": False,
        "likes_count": 0,
        "shares_count": 0,
        "comments_count": 0,
        "remixes": 0,
    }


def test_general_feed_callback_data_stays_within_telegram_limit() -> None:
    keyboard = _keyboard(_card(), "g:r:49", 50)
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data:
                assert len(button.callback_data.encode()) <= 64


def test_profile_feed_callback_data_stays_within_telegram_limit() -> None:
    keyboard = _keyboard(_card(), "p:999999999999:49", 50)
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data:
                assert len(button.callback_data.encode()) <= 64
