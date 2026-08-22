from __future__ import annotations

from copy import deepcopy
from typing import Any

_INSTALLED = False


def install_model_spec_grok_extend_audit() -> None:
    """Keep Grok Extend prompt semantics aligned across billing and provider layers.

    Kie's executable Extend example permits an empty prompt. The public contract
    therefore treats an omitted prompt as the same explicit empty string while
    still rejecting null/non-string values. This installer runs last so older
    audit wrappers cannot re-introduce the stricter missing-key rejection.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_video_contracts as video_contracts
    from app.services import model_catalog as catalog

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def audited_rules(spec: Any, clean: dict[str, Any]) -> None:
        if spec.id == "grok-video-extend":
            if "prompt" not in clean:
                clean["prompt"] = ""
            elif clean["prompt"] is None or not isinstance(clean["prompt"], str):
                raise catalog.InvalidModelParametersError("Grok Extend prompt must be a string")
        previous_rules(spec, clean)

    catalog.ModelCatalog._validate_model_rules = audited_rules

    previous_normalize = video_contracts.normalize_kie_video_input

    def audited_normalize(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        if model == "grok-imagine/extend":
            if "prompt" not in source:
                source["prompt"] = ""
            elif source["prompt"] is None or not isinstance(source["prompt"], str):
                raise video_contracts.KieVideoContractError(
                    "Grok Extend prompt must be a string"
                )

        normalized = previous_normalize(model, source)
        if model == "grok-imagine/extend":
            normalized["prompt"] = source["prompt"]
        return normalized

    video_contracts.normalize_kie_video_input = audited_normalize
