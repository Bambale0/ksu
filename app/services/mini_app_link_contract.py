from __future__ import annotations

import uuid

from app.services.feed_links import (
    mini_app_deep_link,
    post_payload,
    profile_payload,
    remix_payload,
)

_INSTALLED = False


def install_mini_app_link_contract() -> None:
    """Make every newly generated social/referral link open ROXY directly."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services.feed import FeedService

    def post_deep_link(generation_id: uuid.UUID, author_referral_code: str) -> str | None:
        return mini_app_deep_link(post_payload(generation_id, author_referral_code))

    def profile_deep_link(author_referral_code: str) -> str | None:
        return mini_app_deep_link(profile_payload(author_referral_code))

    def remix_deep_link(generation_id: uuid.UUID, author_referral_code: str) -> str | None:
        return mini_app_deep_link(remix_payload(generation_id, author_referral_code))

    FeedService.post_deep_link = staticmethod(post_deep_link)  # type: ignore[method-assign]
    FeedService.profile_deep_link = staticmethod(profile_deep_link)  # type: ignore[method-assign]
    FeedService.remix_deep_link = staticmethod(remix_deep_link)  # type: ignore[method-assign]
