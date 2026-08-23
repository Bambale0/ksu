"""Base contract for post-generation action resolvers.

A resolver turns a finished generation into the payload a Mini App scenario
needs (prefilled prompt/model/settings/refs, target mode, billing hints). It
never executes anything: derivative generations still run exclusively through
the existing generation pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from app.db.models import Generation
from app.services.generation_actions.types import GenerationActionType
from app.services.model_capability import ModelCapabilityResolver
from app.services.model_catalog import ModelCatalog, ModelSpec, UnknownModelError


class ActionResolveError(ValueError):
    """Raised when a generation cannot serve the requested action."""


class BaseActionResolver(ABC):
    action_type: ClassVar[GenerationActionType]

    @abstractmethod
    def resolve(self, generation: Generation) -> dict[str, Any]:
        """Return the scenario payload for this action."""

    # Shared helpers -----------------------------------------------------

    @staticmethod
    def result_media_type(generation: Generation) -> str:
        from app.services.generation_actions.core import GenerationActionService

        return GenerationActionService.media_type(generation)

    @staticmethod
    def source_result_url(generation: Generation) -> str | None:
        from app.services.generation_actions.core import GenerationActionService

        return GenerationActionService.result_url(generation)

    @classmethod
    def default_model(
        cls,
        generation: Generation,
        mode: str,
    ) -> ModelSpec | None:
        """Compatible model for ``mode``; prefers the source model's family."""
        media_type = cls.result_media_type(generation)
        candidates = ModelCapabilityResolver.compatible_specs(media_type, mode)
        if not candidates:
            return None
        candidate_ids = {spec.id for spec in candidates}
        current_id = ""
        try:
            from app.services.generation_actions.core import GenerationActionService

            current_id = GenerationActionService.model_id(generation) or ""
        except Exception:  # pragma: no cover - model_id never raises today
            current_id = ""
        if current_id in candidate_ids:
            return ModelCatalog.get(current_id)
        family = ModelCapabilityResolver.spec_family(current_id)
        same_family = next((spec for spec in candidates if spec.family == family), None)
        return same_family or ModelCapabilityResolver.resolve_fallback(media_type, mode)

    @staticmethod
    def spec_or_none(model_id: str | None) -> ModelSpec | None:
        if not model_id:
            return None
        try:
            return ModelCatalog.get(model_id)
        except UnknownModelError:
            return None
