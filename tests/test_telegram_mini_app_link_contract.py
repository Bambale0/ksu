from __future__ import annotations

import uuid

from app.core.config import settings
from app.services.feed_links import bot_start_link, mini_app_deep_link, post_payload, remix_payload
from app.services.partner import PartnerService


def test_direct_mini_app_link_contract_uses_short_name_path(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    generation_id = uuid.UUID("9de02c55-341a-4fd2-9143-af627bef4173")

    assert mini_app_deep_link("ref_339795159") == (
        "https://t.me/roxy_aicreativebot/app?startapp=ref_339795159"
    )
    assert mini_app_deep_link(post_payload(generation_id, 1400725962)) == (
        "https://t.me/roxy_aicreativebot/app?startapp="
        "feed_9de02c55-341a-4fd2-9143-af627bef4173_ref_1400725962"
    )
    assert mini_app_deep_link(remix_payload(generation_id, 1400725962)) == (
        "https://t.me/roxy_aicreativebot/app?startapp="
        "remix_9de02c55-341a-4fd2-9143-af627bef4173_ref_1400725962"
    )


def test_production_partner_referral_opens_direct_mini_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")

    assert PartnerService.referral_link(339795159) == (
        "https://t.me/roxy_aicreativebot/app?startapp=ref_339795159"
    )
    assert PartnerService.referral_mini_app_link(339795159) == (
        "https://t.me/roxy_aicreativebot/app?startapp=ref_339795159"
    )


def test_missing_short_name_falls_back_to_legacy_bot_link_when_provided(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "")

    assert mini_app_deep_link(
        "ref_339795159",
        fallback_url=bot_start_link("ref_339795159"),
    ) == "https://t.me/roxy_aicreativebot?start=ref_339795159"


def test_short_name_is_sanitized(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "/studio/")

    assert mini_app_deep_link("ref_339795159") == (
        "https://t.me/roxy_aicreativebot/studio?startapp=ref_339795159"
    )


def test_live_bot_username_can_override_stale_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "StaleConfiguredBot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    assert mini_app_deep_link("ref_339795159", bot_username="RealTelegramBot") == (
        "https://t.me/RealTelegramBot/app?startapp=ref_339795159"
    )
