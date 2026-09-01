from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.api.deps import _validated_startapp_inviter
from app.api.v1.feed import _direct_mini_app_link
from app.bot.handlers.launcher import _validated_inviter as _validated_launcher_inviter
from app.core.config import settings
from app.services.feed import FeedService
from app.services.feed_links import parse_feed_deep_link


def test_legacy_feed_bot_link_upgrades_to_tanyapi_main_mini_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_bot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    generation_id = uuid.uuid4()
    legacy = f"https://t.me/roxy_bot?start=feed_{generation_id}_ref_777"
    direct = _direct_mini_app_link(legacy)
    assert direct == f"https://t.me/roxy_bot?startapp=feed_{generation_id}_ref_777"


@pytest.mark.asyncio
async def test_startapp_referral_is_accepted_for_public_post_and_remix_sharer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = uuid.uuid4()

    async def visible(cls, session, value, *, surface):
        del cls, session
        assert value == generation_id
        assert surface == "feed"
        return SimpleNamespace(user_id=uuid.uuid4())

    class Session:
        pass

    monkeypatch.setattr(FeedService, "assert_surface_visible", classmethod(visible))
    session = Session()

    for payload, expected in (
        (f"feed_{generation_id}_ref_777", 777),
        (f"remix_{generation_id}_ref_777", 777),
        (f"feed_{generation_id}_ref_999", 999),
        ("ref_777", 777),
    ):
        assert await _validated_startapp_inviter(session, payload) == expected  # type: ignore[arg-type]
        assert await _validated_launcher_inviter(session, parse_feed_deep_link(payload)) == expected  # type: ignore[arg-type]

    assert await _validated_startapp_inviter(session, "garbage") is None  # type: ignore[arg-type]
    assert await _validated_launcher_inviter(session, parse_feed_deep_link("garbage")) is None  # type: ignore[arg-type]
