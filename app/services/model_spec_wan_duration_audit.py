from __future__ import annotations

from copy import deepcopy
from typing import Any

_INSTALLED = False
_ALLOWED_WAN_EDIT_DURATIONS = {0, *range(2, 11)}


def validate_wan_video_edit_duration(value: Any) -> int:
    """Normalize the current Kie WAN Video Edit duration enum.

    WAN Video Edit is retained as a registered provider/historical contract even
    while it is not admitted for new customer work. Keeping this validator public
    lets contract tests exercise the provider rule without bypassing the product
    admission boundary.
    """

    from app.services.model_catalog import InvalidModelParametersError

    try:
        if isinstance(value, bool):
            raise TypeError
        duration = int(value)
    except (TypeError, ValueError) as exc:
        raise InvalidModelParametersError(
            "Wan 2.7 Video Edit duration must be Auto (0) or 2-10 seconds"
        ) from exc
    if duration not in _ALLOWED_WAN_EDIT_DURATIONS:
        raise InvalidModelParametersError(
            "Wan 2.7 Video Edit duration must be Auto (0) or 2-10 seconds"
        )
    return duration


def install_model_spec_wan_duration_audit() -> None:
    """Enforce the current callable Wan Video Edit duration enum end-to-end."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_video_contracts as video_contracts
    from app.services import model_catalog as catalog

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def audited_rules(spec: Any, clean: dict[str, Any]) -> None:
        if spec.id == "wan-2.7-video-edit":
            clean["duration"] = validate_wan_video_edit_duration(clean.get("duration", 0))
        previous_rules(spec, clean)

    catalog.ModelCatalog._validate_model_rules = audited_rules

    previous_normalize = video_contracts.normalize_kie_video_input

    def audited_normalize(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        if model == "wan/2-7-videoedit":
            try:
                duration = validate_wan_video_edit_duration(source.get("duration", 0))
            except catalog.InvalidModelParametersError as exc:
                raise video_contracts.KieVideoContractError(str(exc)) from exc
            source["duration"] = duration
        return previous_normalize(model, source)

    video_contracts.normalize_kie_video_input = audited_normalize
