from __future__ import annotations

import uuid

from app.core.config import settings
from app.services.feed_links import bot_start_link, mini_app_deep_link, post_payload, remix_payload
from app.services.partner import PartnerService


def test_direct_mini_app_link_contract_matches_tanyapi(monkeypatch) -> None:  # type: ignore[no-untyped-def]
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


def test_production_partner_referral_opens_main_mini_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")

    assert PartnerService.referral_link(339795159) == (
        "https://t.me/roxy_aicreativebot?startapp=ref_339795159"
    )
    assert PartnerService.referral_mini_app_link(339795159) == (
        "https://t.me/roxy_aicreativebot?startapp=ref_339795159"
    )
    assert PartnerService.profile_link(339795159) == (
        "https://t.me/roxy_aicreativebot?startapp=profile_339795159_ref_339795159"
    )


def test_missing_short_name_does_not_fall_back_to_bot_chat(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "")

    assert mini_app_deep_link(
        "ref_339795159",
        fallback_url=bot_start_link("ref_339795159"),
    ) == "https://t.me/roxy_aicreativebot?startapp=ref_339795159"
    assert PartnerService.referral_link(339795159) == (
        "https://t.me/roxy_aicreativebot?startapp=ref_339795159"
    )
    assert PartnerService.profile_link(339795159) == (
        "https://t.me/roxy_aicreativebot?startapp=profile_339795159_ref_339795159"
    )


def test_named_mini_app_short_name_never_changes_public_main_app_link(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "roxy_aicreativebot")
    for short_name in ("app", "studio", "/studio/", "main"):
        monkeypatch.setattr(settings, "telegram_mini_app_short_name", short_name)
        assert mini_app_deep_link("ref_339795159") == (
            "https://t.me/roxy_aicreativebot?startapp=ref_339795159"
        )


def test_live_bot_username_can_override_stale_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "StaleConfiguredBot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")
    assert mini_app_deep_link("ref_339795159", bot_username="RealTelegramBot") == (
        "https://t.me/RealTelegramBot?startapp=ref_339795159"
    )


def test_missing_bot_username_uses_explicit_fallback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "")
    assert mini_app_deep_link("ref_339795159", fallback_url="https://roxy.example/mini-app/") == (
        "https://roxy.example/mini-app/"
    )
