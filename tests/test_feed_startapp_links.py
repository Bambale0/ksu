from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.api.deps import _validated_startapp_inviter
from app.api.v1.feed import _direct_mini_app_link
from app.core.config import settings
from app.services.feed import FeedService
from app.services.feed_links import mini_app_deep_link


def test_feed_share_link_enters_bot_before_mini_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_bot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    generation_id = uuid.uuid4()
    payload = f"feed_{generation_id}_ref_777"
    bot_link = f"https://t.me/roxy_bot?start={payload}"

    assert mini_app_deep_link(payload) == bot_link
    assert _direct_mini_app_link(bot_link) == bot_link


def test_non_feed_social_links_still_open_main_mini_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_bot")
    generation_id = uuid.uuid4()
    payload = f"remix_{generation_id}_ref_777"

    assert mini_app_deep_link(payload) == f"https://t.me/roxy_bot?startapp={payload}"


@pytest.mark.asyncio
async def test_startapp_referral_is_accepted_for_public_post_and_remix_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_id = uuid.uuid4()
    author_user_id = uuid.uuid4()

    async def visible(cls, session, value, *, surface):
        del cls, session
        assert value == generation_id
        assert surface == "feed"
        return SimpleNamespace(user_id=author_user_id)

    class Session:
        async def get(self, model, value):
            del model
            assert value == author_user_id
            return SimpleNamespace(telegram_id=777)

    monkeypatch.setattr(FeedService, "assert_surface_visible", classmethod(visible))
    session = Session()

    assert await _validated_startapp_inviter(session, f"feed_{generation_id}_ref_777") == 777
    assert await _validated_startapp_inviter(session, f"remix_{generation_id}_ref_777") == 777
    assert await _validated_startapp_inviter(session, f"feed_{generation_id}_ref_999") is None
    assert await _validated_startapp_inviter(session, "ref_777") == 777
    assert await _validated_startapp_inviter(session, "garbage") is None
