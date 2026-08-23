from __future__ import annotations

import uuid

from app.core.config import settings
from app.services.feed import FeedService
from app.services.feed_links import mini_app_deep_link, parse_feed_deep_link
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


def test_all_generated_social_links_open_main_mini_app(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    generation_id = uuid.uuid4()

    assert PartnerService.referral_link(123456) == (
        "https://t.me/RoxyExampleBot?startapp=ref_123456"
    )
    assert FeedService.post_deep_link(generation_id, "123456") == (
        f"https://t.me/RoxyExampleBot?startapp=feed_{generation_id}_ref_123456"
    )
    assert FeedService.profile_deep_link("123456") == (
        "https://t.me/RoxyExampleBot?startapp=profile_123456"
    )
    assert FeedService.remix_deep_link(generation_id, "123456") == (
        f"https://t.me/RoxyExampleBot?startapp=remix_{generation_id}_ref_123456"
    )


def test_mini_app_link_rejects_unsafe_payload(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "bot_username", "RoxyExampleBot")
    assert mini_app_deep_link("feed_bad?next=https://evil.example") is None
    assert mini_app_deep_link("x" * 513) is None


def test_invalid_deep_link_does_not_fall_back_to_private_lookup() -> None:
    assert parse_feed_deep_link("feed_not-a-uuid_ref_123") is None
    assert parse_feed_deep_link("posts_secret-user_ref_123") is None
    assert parse_feed_deep_link("profile_secret-user") is None
    assert parse_feed_deep_link("remix_not-a-uuid_ref_123") is None
