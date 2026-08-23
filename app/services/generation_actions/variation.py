"""Variation resolver — fast rerun on the same model and settings."""

from __future__ import annotations

from typing import Any, ClassVar

from app.db.models import Generation
from app.services.generation_actions.base import BaseActionResolver
from app.services.generation_actions.types import GenerationActionType


class VariationResolver(BaseActionResolver):
    """Same model, same settings, new generation.

    The actual spend is protected by the standard billing quote flow: the
    payload marks the action as requiring a fresh quote/confirm step before
    execution, so no ROX can be spent without an explicit confirmation.
    """

    action_type: ClassVar[GenerationActionType] = GenerationActionType.VARIATION

    def resolve(self, generation: Generation) -> dict[str, Any]:
        from app.services.generation_actions.core import GenerationActionService

        model_id = GenerationActionService.model_id(generation)
        model = self.spec_or_none(model_id)
        params = dict(generation.parameters or {})
        settings = GenerationActionService.reusable_parameters(generation, model_id or "")
        return {
            "model": model.id if model else None,
            "prompt": "" if generation.action_type == "trend" else generation.prompt,
            "settings": settings,
            "billing_seconds": params.get("_billing_seconds"),
            # Mini App opens a confirm sheet ("Сгенерировать ещё вариант за X ROX?")
            # instead of charging silently.
            "requires_billing_quote": True,
            "deprecated_model": model is None and bool(model_id),
        }
