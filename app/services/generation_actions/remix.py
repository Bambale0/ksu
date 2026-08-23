"""Remix resolver — editable clone of the original intent."""

from __future__ import annotations

from typing import Any, ClassVar

from app.db.models import Generation
from app.services.generation_actions.base import BaseActionResolver
from app.services.generation_actions.types import GenerationActionType


class RemixResolver(BaseActionResolver):
    """Copy the existing intent: prompt, negative prompt, refs, model, settings."""

    action_type: ClassVar[GenerationActionType] = GenerationActionType.REMIX

    def resolve(self, generation: Generation) -> dict[str, Any]:
        from app.services.generation_actions.core import GenerationActionService

        model = self.default_model(generation, "text_to_image") or self.spec_or_none(
            GenerationActionService.model_id(generation)
        )
        params = dict(generation.parameters or {})
        images, videos = GenerationActionService.parent_references(generation)
        return {
            "prompt": "" if generation.action_type == "trend" else generation.prompt,
            "negative_prompt": params.get("negative_prompt"),
            "refs": {"images": images, "videos": videos},
            "model": model.id if model else None,
            "settings": {
                key: value
                for key, value in params.items()
                if not key.startswith("_")
                and key not in {"negative_prompt"}
                and model is not None
                and key in set(model.known_fields)
            },
        }
