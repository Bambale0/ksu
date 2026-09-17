from __future__ import annotations

from typing import Literal

GenerationProviderName = Literal["kie", "nexus"]

NEXUS_GENERATION_MODELS = frozenset({"nano-banana-pro", "nano-banana-2"})


def provider_for_model(model_id: str) -> GenerationProviderName:
    """Return the production provider for a public model id.

    Keep provider selection centralized so switching a model never relies on UI
    labels, request shape, or a global provider flag.
    """

    return "nexus" if str(model_id) in NEXUS_GENERATION_MODELS else "kie"


def is_nexus_model(model_id: str) -> bool:
    return provider_for_model(model_id) == "nexus"
