from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.api.deps import _validated_startapp_inviter
from app.api.v1.feed import _direct_mini_app_link
from app.services.feed import FeedService


def test_feed_share_link_opens_main_mini_app_without_changing_payload() -> None:
    generation_id = uuid.uuid4()
    legacy = f"https://t.me/roxy_bot?start=feed_{generation_id}_ref_777"
    direct = _direct_mini_app_link(legacy)
    assert direct == f"https://t.me/roxy_bot?startapp=feed_{generation_id}_ref_777"
    assert len(f"feed_{generation_id}_ref_777") <= 64


@pytest.mark.asyncio
async def test_startapp_referral_is_accepted_only_for_the_public_work_author(
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
    assert await _validated_startapp_inviter(session, f"feed_{generation_id}_ref_999") is None
    assert await _validated_startapp_inviter(session, f"remix_{generation_id}_ref_777") is None
    assert await _validated_startapp_inviter(session, "garbage") is None
