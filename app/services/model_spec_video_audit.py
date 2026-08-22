from __future__ import annotations

from copy import deepcopy
from typing import Any

_INSTALLED = False


def _kling_top_duration(value: Any, *, error_type: type[Exception]) -> int:
    try:
        if isinstance(value, bool):
            raise TypeError
        duration = int(value)
    except (TypeError, ValueError) as exc:
        raise error_type("Kling duration must be an integer between 3 and 15 seconds") from exc
    if not 3 <= duration <= 15:
        raise error_type("Kling duration must be between 3 and 15 seconds")
    return duration


def install_model_spec_video_audit() -> None:
    """Harden Kling 3.0 and Veo 3.1 against their current Kie contracts."""

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_video_contracts as video_contracts
    from app.services import model_catalog as catalog
    from app.services import model_ui_contract as ui_contract

    # With first/last frames Kling auto-adapts aspect ratio. Keeping a global
    # 16:9 default caused the frame flow to submit an otherwise unnecessary
    # parameter and defeated that provider behavior.
    ui_contract.MODEL_DEFAULTS.setdefault("kling-3.0", {}).pop("aspect_ratio", None)

    # Keep public Veo choices on the current Quality/Fast/Lite product surface.
    veo_fields = ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("veo-3.1", {})
    veo_fields["veo_model"] = ["veo3", "veo3_fast", "veo3_lite"]
    veo_fields["aspect_ratio"] = ["16:9", "9:16", "auto"]
    veo_fields["generation_type"] = [
        "TEXT_2_VIDEO",
        "FIRST_AND_LAST_FRAMES_2_VIDEO",
        "REFERENCE_2_VIDEO",
    ]

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def audited_rules(spec: Any, clean: dict[str, Any]) -> None:
        if spec.id == "kling-3.0" and clean.get("multi_shots"):
            # The legacy rule required sum(multi_prompt.duration) == duration.
            # Kie's current docs define per-shot duration plus an overall 15s
            # storyboard cap; the provider's own example does not satisfy that
            # equality. Run all legacy element/shot validation except that check.
            shadow = deepcopy(clean)
            shadow.pop("duration", None)
            previous_rules(spec, shadow)
        else:
            previous_rules(spec, clean)

        if spec.id == "kling-3.0":
            images = clean.get("image_urls") or []
            if images and clean.get("aspect_ratio") not in (None, ""):
                raise catalog.InvalidModelParametersError(
                    "Kling aspect_ratio must be omitted when first/last frame images are provided"
                )
            if clean.get("multi_shots"):
                # Duration remains a real top-level provider field even though it
                # no longer has to equal the storyboard sum. Validate it explicitly
                # because the legacy equality bypass removes it from the shadow.
                clean["duration"] = _kling_top_duration(
                    clean.get("duration"), error_type=catalog.InvalidModelParametersError
                )
                shots = clean.get("multi_prompt") or []
                if not isinstance(shots, list) or not 1 <= len(shots) <= 5:
                    raise catalog.InvalidModelParametersError(
                        "Kling multi-shot requires one to five shots"
                    )
                total = 0
                for shot in shots:
                    try:
                        total += int(shot.get("duration"))
                    except (AttributeError, TypeError, ValueError) as exc:
                        raise catalog.InvalidModelParametersError(
                            "Every Kling shot requires an integer duration"
                        ) from exc
                if total > 15:
                    raise catalog.InvalidModelParametersError(
                        "Kling multi-shot storyboard must not exceed 15 seconds"
                    )

        if spec.id == "veo-3.1":
            model = str(clean.get("veo_model") or "veo3_fast")
            if model not in {"veo3", "veo3_fast", "veo3_lite"}:
                raise catalog.InvalidModelParametersError(
                    "Veo 3.1 model must be veo3, veo3_fast or veo3_lite"
                )
            images = clean.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 3:
                raise catalog.InvalidModelParametersError(
                    "Veo 3.1 accepts at most three image references"
                )
            generation_type = str(clean.get("generation_type") or "TEXT_2_VIDEO")
            aspect = str(clean.get("aspect_ratio") or "16:9").lower()
            if generation_type == "TEXT_2_VIDEO" and images:
                raise catalog.InvalidModelParametersError(
                    "Veo TEXT_2_VIDEO cannot include image references; use first/last-frame or reference mode"
                )
            if generation_type == "FIRST_AND_LAST_FRAMES_2_VIDEO" and not 1 <= len(images) <= 2:
                raise catalog.InvalidModelParametersError(
                    "Veo first/last-frame mode requires one or two images"
                )
            if generation_type == "REFERENCE_2_VIDEO":
                if not 1 <= len(images) <= 3:
                    raise catalog.InvalidModelParametersError(
                        "Veo reference mode requires one to three images"
                    )
                if model not in {"veo3_fast", "veo3_lite"}:
                    raise catalog.InvalidModelParametersError(
                        "Veo reference mode is available only on Fast or Lite"
                    )
                if aspect not in {"16:9", "9:16"}:
                    raise catalog.InvalidModelParametersError(
                        "Veo reference mode requires 16:9 or 9:16 aspect ratio"
                    )

    catalog.ModelCatalog._validate_model_rules = audited_rules

    previous_video_normalizer = video_contracts.normalize_kie_video_input
    previous_veo_normalizer = video_contracts.normalize_kie_veo_input

    def audited_video_normalizer(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        if model != "kling-3.0/video":
            return previous_video_normalizer(model, source)

        images = source.get("image_urls") or []
        if images and source.get("aspect_ratio") not in (None, ""):
            raise video_contracts.KieVideoContractError(
                "Kling aspect_ratio must be omitted when first/last frame images are provided"
            )

        if source.get("multi_shots"):
            top_duration = _kling_top_duration(
                source.get("duration"), error_type=video_contracts.KieVideoContractError
            )
            shots = source.get("multi_prompt") or []
            if not isinstance(shots, list) or not 1 <= len(shots) <= 5:
                raise video_contracts.KieVideoContractError(
                    "Kling multi-shot requires one to five shots"
                )
            total = 0
            for shot in shots:
                try:
                    total += int(shot.get("duration"))
                except (AttributeError, TypeError, ValueError) as exc:
                    raise video_contracts.KieVideoContractError(
                        "Every Kling shot requires an integer duration"
                    ) from exc
            if total > 15:
                raise video_contracts.KieVideoContractError(
                    "Kling multi-shot storyboard must not exceed 15 seconds"
                )

            # Bypass only the stale equality rule, then restore the validated
            # top-level provider field after all other Kling validation.
            provider_source = deepcopy(source)
            provider_source.pop("duration", None)
            normalized = previous_video_normalizer(model, provider_source)
            normalized["duration"] = top_duration
            return normalized

        return previous_video_normalizer(model, source)

    def audited_veo_normalizer(input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        model = str(source.get("veo_model") or "veo3_fast")
        if model not in {"veo3", "veo3_fast", "veo3_lite"}:
            raise video_contracts.KieVideoContractError(
                "Veo 3.1 model must be veo3, veo3_fast or veo3_lite"
            )
        images = source.get("image_urls") or []
        if not isinstance(images, list) or len(images) > 3:
            raise video_contracts.KieVideoContractError(
                "Veo 3.1 accepts at most three image references"
            )
        generation_type = str(source.get("generation_type") or "TEXT_2_VIDEO")
        aspect = str(source.get("aspect_ratio") or "16:9").lower()
        if generation_type == "TEXT_2_VIDEO" and images:
            raise video_contracts.KieVideoContractError(
                "Veo TEXT_2_VIDEO cannot include image references"
            )
        if generation_type == "FIRST_AND_LAST_FRAMES_2_VIDEO" and not 1 <= len(images) <= 2:
            raise video_contracts.KieVideoContractError(
                "Veo first/last-frame mode requires one or two images"
            )
        if generation_type == "REFERENCE_2_VIDEO":
            if not 1 <= len(images) <= 3:
                raise video_contracts.KieVideoContractError(
                    "Veo reference mode requires one to three images"
                )
            if model not in {"veo3_fast", "veo3_lite"}:
                raise video_contracts.KieVideoContractError(
                    "Veo reference mode is available only on Fast or Lite"
                )
            if aspect not in {"16:9", "9:16"}:
                raise video_contracts.KieVideoContractError(
                    "Veo reference mode requires 16:9 or 9:16 aspect ratio"
                )
        return previous_veo_normalizer(source)

    video_contracts.normalize_kie_video_input = audited_video_normalizer
    video_contracts.normalize_kie_veo_input = audited_veo_normalizer
