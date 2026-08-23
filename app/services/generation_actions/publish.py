"""Publish resolver — result becomes a feed post with a share payload."""

from __future__ import annotations

from typing import Any, ClassVar

from app.db.models import Generation
from app.services.generation_actions.base import ActionResolveError, BaseActionResolver
from app.services.generation_actions.types import GenerationActionType


class PublishResolver(BaseActionResolver):
    """Validate that a result can be published and build its share payload.

    Publishing itself stays in :mod:`app.services.feed` (durable static media,
    scope rules, adult-content downgrade). This resolver only answers the
    action-context questions: can this generation be published by this user,
    and what should the success screen show.
    """

    action_type: ClassVar[GenerationActionType] = GenerationActionType.PUBLISH

    def resolve(self, generation: Generation) -> dict[str, Any]:
        if generation.source_feed_gen_id is not None:
            raise ActionResolveError("Derivative generations cannot be published to feed")
        return {
            "publishable": True,
            "publication_scope": generation.publication_scope,
            "already_published": bool(generation.is_public_feed),
        }

    def share_payload(self, generation: Generation, author_telegram_id: int) -> dict[str, Any]:
        """Normalized {post_id, post_url, share_url, share_text} for success UI."""
        from app.services.feed import FeedService

        payload = FeedService.share_payload(generation, author_telegram_id)
        raw_post_url = FeedService.post_deep_link(generation.id, str(author_telegram_id))
        return {
            "post_id": str(generation.id),
            "post_url": raw_post_url,
            "share_url": payload.get("share_url"),
            "share_text": payload.get("share_text"),
            "copy_link": payload.get("copy_link"),
        }
