from __future__ import annotations

from typing import Any

_INSTALLED = False


def install_model_spec_motion_audit() -> None:
    """Apply current Kling Motion orientation-dependent limits."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import model_catalog as catalog

    previous_prepare = catalog.ModelCatalog.prepare

    def audited_prepare(
        cls: type[catalog.ModelCatalog],
        model_id: str,
        parameters: dict[str, Any],
        *,
        billing_seconds: int | None = None,
    ):
        result = previous_prepare(model_id, parameters, billing_seconds=billing_seconds)
        spec, clean, _cost, seconds, _unit = result
        if spec.id in {"kling-motion-2.6", "kling-motion-3.0"}:
            prompt = str(clean.get("prompt") or "")
            if len(prompt) > 2500:
                raise catalog.InvalidModelParametersError(
                    "Kling Motion prompt must be at most 2500 characters"
                )
            orientation = str(clean.get("character_orientation") or "image")
            if orientation == "image" and seconds is not None and seconds > 10:
                raise catalog.InvalidModelParametersError(
                    "Kling Motion with image orientation supports motion videos up to 10 seconds"
                )
            if orientation == "video" and seconds is not None and seconds > 30:
                raise catalog.InvalidModelParametersError(
                    "Kling Motion with video orientation supports motion videos up to 30 seconds"
                )
        return result

    catalog.ModelCatalog.prepare = classmethod(audited_prepare)
