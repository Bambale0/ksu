from __future__ import annotations

import uuid

from app.core.config import settings
from app.services.feed_links import mini_app_deep_link, post_payload, remix_payload


def test_social_links_use_direct_mini_app_short_name(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    generation_id = uuid.UUID("9de02c55-341a-4fd2-9143-af627bef4173")

    assert mini_app_deep_link(post_payload(generation_id, 1400725962)) == (
        "https://t.me/roxy_aicreativebot/app?startapp="
        "feed_9de02c55-341a-4fd2-9143-af627bef4173_ref_1400725962"
    )
    assert mini_app_deep_link(remix_payload(generation_id, 1400725962)) == (
        "https://t.me/roxy_aicreativebot/app?startapp="
        "remix_9de02c55-341a-4fd2-9143-af627bef4173_ref_1400725962"
    )
