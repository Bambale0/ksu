"""Post-generation action platform.

Public API is backwards compatible with the former single-module
``app/services/generation_actions.py``: everything re-exported here keeps its
original name and location, so existing imports keep working.
"""

from __future__ import annotations

from app.services.generation_actions.animate import AnimateResolver
from app.services.generation_actions.base import ActionResolveError, BaseActionResolver
from app.services.generation_actions.core import (
    ACTION_ALIASES,
    DERIVATIVE_ACTIONS,
    IMAGE_ACTIONS,
    VIDEO_AUDIO_ACTIONS,
    GenerationAction,
    GenerationActionService,
)
from app.services.generation_actions.edit_image import EditImageResolver
from app.services.generation_actions.publish import PublishResolver
from app.services.generation_actions.remix import RemixResolver
from app.services.generation_actions.types import (
    DERIVATIVE_ACTION_TYPES,
    GenerationActionType,
)
from app.services.generation_actions.variation import VariationResolver

# Registry used by the action-context layer to build scenario payloads.
ACTION_RESOLVERS: dict[str, BaseActionResolver] = {
    resolver.action_type: resolver
    for resolver in (
        RemixResolver(),
        VariationResolver(),
        EditImageResolver(),
        AnimateResolver(),
        PublishResolver(),
    )
}


def resolver_for(action: str) -> BaseActionResolver | None:
    action_type = GenerationActionType.from_wire(ACTION_ALIASES.get(action, action))
    return ACTION_RESOLVERS.get(action_type)


__all__ = [
    "ACTION_ALIASES",
    "ACTION_RESOLVERS",
    "DERIVATIVE_ACTIONS",
    "DERIVATIVE_ACTION_TYPES",
    "IMAGE_ACTIONS",
    "VIDEO_AUDIO_ACTIONS",
    "ActionResolveError",
    "AnimateResolver",
    "BaseActionResolver",
    "EditImageResolver",
    "GenerationAction",
    "GenerationActionService",
    "GenerationActionType",
    "PublishResolver",
    "RemixResolver",
    "VariationResolver",
    "resolver_for",
]
