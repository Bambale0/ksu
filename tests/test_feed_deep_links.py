from __future__ import annotations

import uuid

from app.services.feed_links import parse_feed_deep_link


def test_feed_post_deep_link_parses() -> None:
    generation_id = uuid.uuid4()
    link = parse_feed_deep_link(f"feed_{generation_id}_ref_123456")
    assert link is not None
    assert link.action == "feed"
    assert link.generation_id == generation_id
    assert link.referral_telegram_id == 123456


def test_profile_deep_link_parses() -> None:
    link = parse_feed_deep_link("posts_123456_ref_123456")
    assert link is not None
    assert link.action == "posts"
    assert link.profile_referral_code == "123456"
    assert link.referral_telegram_id == 123456


def test_remix_deep_link_is_distinct_action() -> None:
    generation_id = uuid.uuid4()
    link = parse_feed_deep_link(f"remix_{generation_id}_ref_123456")
    assert link is not None
    assert link.action == "remix"
    assert link.generation_id == generation_id


def test_invalid_deep_link_does_not_fall_back_to_private_lookup() -> None:
    assert parse_feed_deep_link("feed_not-a-uuid_ref_123") is None
    assert parse_feed_deep_link("posts_secret-user_ref_123") is None
    assert parse_feed_deep_link("remix_not-a-uuid_ref_123") is None
