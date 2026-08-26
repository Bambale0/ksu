from __future__ import annotations

import uuid

from app.services.feed_links import (
    bot_start_link,
    mini_app_deep_link,
    post_payload,
    profile_payload,
    referral_payload,
    remix_payload,
)

_INSTALLED = False


def install_mini_app_link_contract() -> None:
    """Make social links open ROXY and partner links use the proven bot path."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services.feed import FeedService
    from app.services.partner import PartnerService

    def post_deep_link(generation_id: uuid.UUID, author_referral_code: str) -> str | None:
        return mini_app_deep_link(post_payload(generation_id, author_referral_code))

    def profile_deep_link(author_referral_code: str) -> str | None:
        return mini_app_deep_link(profile_payload(author_referral_code))

    def remix_deep_link(generation_id: uuid.UUID, author_referral_code: str) -> str | None:
        return mini_app_deep_link(remix_payload(generation_id, author_referral_code))

    def referral_link(telegram_id: int) -> str | None:
        # Matches banano_kling:tanyapi for public partner sharing: open the bot
        # with /start first, then the bot launches the WebApp with payload
        # preserved. This avoids BOT_INVALID on Telegram Main Mini App links.
        return bot_start_link(referral_payload(telegram_id))

    FeedService.post_deep_link = staticmethod(post_deep_link)  # type: ignore[method-assign]
    FeedService.profile_deep_link = staticmethod(profile_deep_link)  # type: ignore[method-assign]
    FeedService.remix_deep_link = staticmethod(remix_deep_link)  # type: ignore[method-assign]
    PartnerService.referral_link = staticmethod(referral_link)  # type: ignore[method-assign]
