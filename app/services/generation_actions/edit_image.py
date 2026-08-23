"""Edit-image resolver — result becomes the input image of an i2i run."""

from __future__ import annotations

from typing import Any, ClassVar

from app.db.models import Generation
from app.services.generation_actions.base import ActionResolveError, BaseActionResolver
from app.services.generation_actions.types import GenerationActionType
from app.services.model_capability import MODE_IMAGE_TO_IMAGE


class EditImageResolver(BaseActionResolver):
    """Source media must be an image; mode is forced to ``image_to_image``.

    The compatible model is resolved through :class:`ModelCapabilityResolver`
    (edit-capable image models first, same family preferred, deterministic
    fallback otherwise). Video results are rejected here; the animate resolver
    owns that path.
    """

    action_type: ClassVar[GenerationActionType] = GenerationActionType.EDIT_IMAGE

    def resolve(self, generation: Generation) -> dict[str, Any]:

        if self.result_media_type(generation) != "image":
            raise ActionResolveError("Edit action requires an image generation result")
        source_url = self.source_result_url(generation)
        if not source_url:
            raise ActionResolveError("Generation has no reusable image result")

        model = self.default_model(generation, MODE_IMAGE_TO_IMAGE)
        return {
            "mode": MODE_IMAGE_TO_IMAGE,
            "source_media": {"type": "image", "url": source_url},
            "model": model.id if model else None,
            "prompt": None,
            "settings": {},
            "input_url": source_url,
            "edit_presets": [
                {"id": "clothes", "label": "Одежда"},
                {"id": "hair", "label": "Причёска"},
                {"id": "hair_color", "label": "Цвет волос"},
                {"id": "nails", "label": "Ногти"},
                {"id": "background", "label": "Фон"},
                {"id": "style", "label": "Стиль"},
                {"id": "details", "label": "Детали"},
                {"id": "custom", "label": "Своё"},
            ],
        }
