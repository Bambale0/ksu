from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

_INSTALLED = False
_VIDEO_INPUT_ALIASES = ("input_video_url", "input_video_urls", "input_video")
T = TypeVar("T")


def _extend_unique(values: Iterable[T], *extra: T) -> tuple[T, ...]:
    return tuple(dict.fromkeys((*values, *extra)))


def install_seedance_video_alias_contract() -> None:
    """Accept Mini App video upload aliases before Seedance validation/billing.

    Some Mini App surfaces send uploaded video references as ``input_video_url``.
    Seedance provider contracts use ``reference_video_urls``. The conversion must
    happen at the model-routing boundary, before the strict Seedance validator
    runs, otherwise the task can fail locally and never reach Kie.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import model_routing

    model_routing.LEGACY_VIDEO_REFERENCE_FIELDS = _extend_unique(
        model_routing.LEGACY_VIDEO_REFERENCE_FIELDS,
        *_VIDEO_INPUT_ALIASES,
    )
    model_routing.VIDEO_REFERENCE_FIELDS = _extend_unique(
        model_routing.VIDEO_REFERENCE_FIELDS,
        *_VIDEO_INPUT_ALIASES,
    )
    model_routing.SEEDANCE_GENERAL_VIDEO_REFERENCE_FIELDS = _extend_unique(
        model_routing.SEEDANCE_GENERAL_VIDEO_REFERENCE_FIELDS,
        *_VIDEO_INPUT_ALIASES,
    )
    model_routing.REFERENCE_PARAMETER_FIELDS = frozenset(
        (*model_routing.IMAGE_REFERENCE_FIELDS, *model_routing.VIDEO_REFERENCE_FIELDS)
    )

    # ReferenceResolver imports constants by value, so patch its runtime contract
    # too when it is available. Importing it here is safe: ``model_routing`` has
    # already been updated first, so late imports see the canonical aliases.
    from app.services import reference_resolver

    reference_resolver.EXPLICIT_MEDIA_INPUT_FIELDS = _extend_unique(
        reference_resolver.EXPLICIT_MEDIA_INPUT_FIELDS,
        *_VIDEO_INPUT_ALIASES,
    )
    reference_resolver.PUBLIC_VIDEO_REFERENCE_FIELDS = _extend_unique(
        reference_resolver.PUBLIC_VIDEO_REFERENCE_FIELDS,
        *_VIDEO_INPUT_ALIASES,
    )
