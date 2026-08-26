from __future__ import annotations

import uuid

from app.core.config import settings
from app.services.feed_links import bot_start_link, mini_app_deep_link, post_payload, remix_payload
from app.services.partner import PartnerService


def test_app_placeholder_uses_main_mini_app_link(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    generation_id = uuid.UUID("9de02c55-341a-4fd2-9143-af627bef4173")

    assert mini_app_deep_link("ref_339795159") == (
        "https://t.me/roxy_aicreativebot?startapp=ref_339795159"
    )
    assert mini_app_deep_link(post_payload(generation_id, 1400725962)) == (
        "https://t.me/roxy_aicreativebot?startapp="
        "feed_9de02c55-341a-4fd2-9143-af627bef4173_ref_1400725962"
    )
    assert mini_app_deep_link(remix_payload(generation_id, 1400725962)) == (
        "https://t.me/roxy_aicreativebot?startapp="
        "remix_9de02c55-341a-4fd2-9143-af627bef4173_ref_1400725962"
    )


def test_production_partner_referral_uses_tanyapi_bot_link(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")

    assert PartnerService.referral_link(339795159) == (
        "https://t.me/roxy_aicreativebot?start=ref_339795159"
    )
    assert PartnerService.referral_link(339795159) == bot_start_link("ref_339795159")
    assert PartnerService.referral_mini_app_link(339795159) == (
        "https://t.me/roxy_aicreativebot?startapp=ref_339795159"
    )


def test_real_direct_mini_app_short_name_keeps_path_segment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "studio")

    assert mini_app_deep_link("ref_339795159") == (
        "https://t.me/roxy_aicreativebot/studio?startapp=ref_339795159"
    )
