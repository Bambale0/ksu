from __future__ import annotations

import uuid
from typing import Any

_INSTALLED = False


def install_feed_repeat_contract() -> None:
    """Expose repeat availability independently from prompt visibility.

    Public feed authors may hide their prompt. That privacy choice must not hide
    the product-level Repeat action: the server can reuse the source prompt and
    settings without returning the prompt text to the viewer. Keep derivatives,
    trends and models that are no longer callable non-repeatable.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.db.models import Generation
    from app.services.feed import FeedService
    from app.services.model_catalog import ModelCatalog, UnknownModelError

    previous_to_card = FeedService.to_card

    def repeat_allowed(generation: Generation) -> bool:
        if generation.source_feed_gen_id is not None or generation.action_type == "trend":
            return False
        model_id = str((generation.parameters or {}).get("_model_id") or "").strip()
        if not model_id:
            return False
        try:
            ModelCatalog.get(model_id)
        except UnknownModelError:
            return False
        return True

    @classmethod
    async def card_with_repeat(
        cls,
        session,
        generation: Generation,
        *,
        viewer_user_id: uuid.UUID,
        surface: str,
    ) -> dict[str, Any]:  # type: ignore[no-untyped-def]
        card = await previous_to_card(
            session,
            generation,
            viewer_user_id=viewer_user_id,
            surface=surface,
        )
        allowed = repeat_allowed(generation)
        # Existing Mini App surfaces read prompt_actions_allowed for the Repeat
        # button. Keep that compatibility field, but make it about server-side
        # reuse capability rather than whether the prompt text is visible.
        card["prompt_actions_allowed"] = allowed
        card["repeat_allowed"] = allowed
        return card

    FeedService.to_card = card_with_repeat
