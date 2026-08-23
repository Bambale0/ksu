"""Animate resolver — image result becomes the source frame of an i2v run."""

from __future__ import annotations

from typing import Any, ClassVar

from app.db.models import Generation
from app.services.generation_actions.base import ActionResolveError, BaseActionResolver
from app.services.generation_actions.types import GenerationActionType
from app.services.model_capability import MODE_IMAGE_TO_VIDEO


class AnimateResolver(BaseActionResolver):
    """Source media must be an image; mode is forced to ``image_to_video``.

    The compatible video model is resolved through
    :class:`ModelCapabilityResolver`; when the source family has no i2v-capable
    model the deterministic platform fallback is used instead of failing.
    """

    action_type: ClassVar[GenerationActionType] = GenerationActionType.ANIMATE

    def resolve(self, generation: Generation) -> dict[str, Any]:
        if self.result_media_type(generation) != "image":
            raise ActionResolveError("Animate action requires an image generation result")
        source_url = self.source_result_url(generation)
        if not source_url:
            raise ActionResolveError("Generation has no reusable image result")

        model = self.default_model(generation, MODE_IMAGE_TO_VIDEO)
        return {
            "mode": MODE_IMAGE_TO_VIDEO,
            "source_media": {"type": "image", "url": source_url},
            "model": model.id if model else None,
            "prompt": None,
            "settings": {
                # Sensible defaults; the ui_schema still governs what is shown.
                "duration": model.min_seconds if model else None,
                "aspect_ratio": None,
            },
            "input_url": source_url,
        }
