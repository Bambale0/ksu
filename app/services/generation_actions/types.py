"""Canonical generation action types.

The platform speaks in these enum values; the legacy wire ids used by the Mini
App and the Telegram bot (``remix``, ``repeat``, ``edit``, ``animate``,
``publish``) are kept as stable string values so no existing flow breaks.
"""

from __future__ import annotations

from enum import StrEnum


class GenerationActionType(StrEnum):
    REMIX = "remix"
    VARIATION = "repeat"
    EDIT_IMAGE = "edit"
    ANIMATE = "animate"
    PUBLISH = "publish"
    OPEN_RESULT = "open_result"

    @classmethod
    def from_wire(cls, action: str) -> "GenerationActionType":
        """Map any historical alias onto the canonical enum member."""
        aliases = {"new_prompt": cls.VARIATION, "parameters": cls.VARIATION}
        try:
            return cls(action)
        except ValueError:
            return aliases.get(action, cls.OPEN_RESULT)


# Actions that spawn a derivative generation through the existing pipeline.
DERIVATIVE_ACTION_TYPES = frozenset(
    {
        GenerationActionType.REMIX,
        GenerationActionType.VARIATION,
        GenerationActionType.EDIT_IMAGE,
        GenerationActionType.ANIMATE,
    }
)
