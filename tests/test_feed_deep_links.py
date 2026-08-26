from __future__ import annotations

import uuid

from app.core.config import settings
from app.services.feed import FeedService
from app.services.feed_links import (
    bot_start_link,
    mini_app_deep_link,
    parse_feed_deep_link,
    post_payload,
    profile_payload,
    referral_payload,
    remix_payload,
)
from app.services.partner import PartnerService


def test_feed_post_deep_link_parses() -> None:
    generation_id = uuid.uuid4()
    link = parse_feed_deep_link(f"feed_{generation_id}_ref_123456")
    assert link is not None
    assert link.action == "feed"
    assert link.generation_id == generation_id
    assert link.referral_telegram_id == 123456


def test_profile_deep_link_parses() -> None:
    legacy = parse_feed_deep_link("posts_123456_ref_123456")
    direct = parse_feed_deep_link("profile_123456")
    signed_direct = parse_feed_deep_link("profile_123456_ref_123456")
    for link in (legacy, direct, signed_direct):
        assert link is not None
        assert link.action == "posts"
        assert link.profile_referral_code == "123456"
        assert link.referral_telegram_id == 123456


def test_profile_deep_link_rejects_mismatched_referral() -> None:
    assert parse_feed_deep_link("posts_123456_ref_999999") is None
    assert parse_feed_deep_link("profile_123456_ref_999999") is None


def test_remix_deep_link_is_distinct_action() -> None:
    generation_id = uuid.uuid4()
    link = parse_feed_deep_link(f"remix_{generation_id}_ref_123456")
    assert link is not None
    assert link.action == "remix"
    assert link.generation_id == generation_id


def test_partner_referral_link_opens_bot_like_tanyapi(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "app")

    link = PartnerService.referral_link(123456)

    assert link == "https://t.me/RoxyExampleBot?start=ref_123456"
    assert "startapp" not in link
    parsed = parse_feed_deep_link(link.rsplit("start=", 1)[1])
    assert parsed is not None
    assert parsed.action == "ref"
    assert parsed.referral_telegram_id == 123456


def test_referral_payloads_round_trip_for_share_surfaces() -> None:
    generation_id = uuid.uuid4()

    referral = parse_feed_deep_link(referral_payload(123456))
    post = parse_feed_deep_link(post_payload(generation_id, 123456))
    profile = parse_feed_deep_link(profile_payload(123456))
    remix = parse_feed_deep_link(remix_payload(generation_id, 123456))

    assert referral is not None
    assert referral.action == "ref"
    assert referral.referral_telegram_id == 123456

    assert post is not None
    assert post.action == "feed"
    assert post.generation_id == generation_id
    assert post.referral_telegram_id == 123456

    assert profile is not None
    assert profile.action == "posts"
    assert profile.profile_referral_code == "123456"
    assert profile.referral_telegram_id == 123456

    assert remix is not None
    assert remix.action == "remix"
    assert remix.generation_id == generation_id
    assert remix.referral_telegram_id == 123456


def test_all_generated_social_links_keep_main_mini_app_except_partner_bot_link(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "studio")
    generation_id = uuid.uuid4()

    assert PartnerService.referral_link(123456) == (
        "https://t.me/RoxyExampleBot?start=ref_123456"
    )
    assert PartnerService.referral_mini_app_link(123456) == (
        "https://t.me/RoxyExampleBot?startapp=ref_123456"
    )
    assert FeedService.post_deep_link(generation_id, "123456") == (
        f"https://t.me/RoxyExampleBot?startapp=feed_{generation_id}_ref_123456"
    )
    assert FeedService.profile_deep_link("123456") == (
        "https://t.me/RoxyExampleBot?startapp=profile_123456_ref_123456"
    )
    assert FeedService.remix_deep_link(generation_id, "123456") == (
        f"https://t.me/RoxyExampleBot?startapp=remix_{generation_id}_ref_123456"
    )


def test_short_name_setting_is_irrelevant_for_main_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    for short_name in ("", "app", "main", "default", "roxy", "/studio/"):
        monkeypatch.setattr(settings, "telegram_mini_app_short_name", short_name)
        assert mini_app_deep_link("ref_123456") == (
            "https://t.me/RoxyExampleBot?startapp=ref_123456"
        )


def test_mini_app_link_encodes_payload_like_tanyapi(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    monkeypatch.setattr(settings, "telegram_mini_app_short_name", "roxy")
    assert mini_app_deep_link("prompt_hello world_ref_ABC") == (
        "https://t.me/RoxyExampleBot?startapp=prompt_hello%20world_ref_ABC"
    )
    assert mini_app_deep_link("") == "https://t.me/RoxyExampleBot?startapp"
    assert bot_start_link("ref_123456") == "https://t.me/RoxyExampleBot?start=ref_123456"


def test_invalid_deep_link_does_not_fall_back_to_private_lookup() -> None:
    assert parse_feed_deep_link("feed_not-a-uuid_ref_123") is None
    assert parse_feed_deep_link("posts_secret-user_ref_123") is None
    assert parse_feed_deep_link("profile_secret-user") is None
    assert parse_feed_deep_link("remix_not-a-uuid_ref_123") is None
