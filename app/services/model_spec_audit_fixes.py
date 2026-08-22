from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

_INSTALLED = False
_MISSING = object()


def _require_bool(payload: dict[str, Any], field: str) -> None:
    value = payload.get(field)
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")


def install_model_spec_audit_fixes() -> None:
    """Final provider-boundary guards discovered by the post-merge model audit.

    This installer runs after the existing provider sync/guards. It intentionally
    validates the same constraints at both ModelCatalog (pre-billing) and the final
    Kie payload boundary so recovery/replay paths cannot bypass the public contract.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_video_contracts as video_contracts
    from app.services import model_catalog as catalog
    from app.services import model_ui_contract as ui_contract

    # Current Kie Seedance 2.0 / Fast / Mini request docs expose
    # return_last_frame. The older compatibility sync removed it, leaving a
    # real provider capability unavailable in ROXY.
    seedance20_ids = {"seedance-2.0", "seedance-2.0-fast", "seedance-2.0-mini"}
    patched_specs = []
    for spec in catalog.SPECS:
        if spec.id in seedance20_ids and "return_last_frame" not in spec.known_fields:
            fields = list(spec.known_fields)
            # Keep the result option next to generate_audio when possible.
            try:
                index = fields.index("generate_audio")
            except ValueError:
                index = len(fields) - 1
            fields.insert(index + 1, "return_last_frame")
            spec = replace(spec, known_fields=tuple(fields))
        patched_specs.append(spec)
    catalog.SPECS = tuple(patched_specs)
    catalog.ModelCatalog._by_id = {spec.id: spec for spec in catalog.SPECS}
    for model_id in seedance20_ids:
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["return_last_frame"] = False

    previous_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def audited_rules(spec: Any, clean: dict[str, Any]) -> None:
        previous_rules(spec, clean)

        if spec.id in seedance20_ids:
            frame_mode = bool(clean.get("first_frame_url") or clean.get("last_frame_url"))
            reference_mode = bool(
                clean.get("reference_image_urls")
                or clean.get("reference_video_urls")
                or clean.get("reference_audio_urls")
            )
            if frame_mode and reference_mode:
                raise catalog.InvalidModelParametersError(
                    "Seedance first/last-frame mode and multimodal reference mode are mutually exclusive"
                )
            value = clean.get("return_last_frame")
            if value is not None and not isinstance(value, bool):
                raise catalog.InvalidModelParametersError("Seedance return_last_frame must be boolean")

        if spec.id in {"grok-video-t2v", "grok-video-i2v"}:
            mode = str(clean.get("mode") or "normal")
            if mode not in {"fun", "normal", "spicy"}:
                raise catalog.InvalidModelParametersError("Grok mode must be fun, normal or spicy")
            resolution = str(clean.get("resolution") or "480p")
            if resolution not in {"480p", "720p", "1080p"}:
                raise catalog.InvalidModelParametersError(
                    "Grok resolution must be 480p, 720p or 1080p"
                )
            ratio = str(clean.get("aspect_ratio") or "16:9")
            if ratio not in {"2:3", "3:2", "1:1", "16:9", "9:16"}:
                raise catalog.InvalidModelParametersError("Unsupported Grok aspect ratio")
            nsfw = clean.get("nsfw_checker")
            if nsfw is not None and not isinstance(nsfw, bool):
                raise catalog.InvalidModelParametersError("Grok nsfw_checker must be boolean")

        if spec.id == "grok-video-upscale":
            resolution = str(clean.get("resolution") or "1080p")
            if resolution not in {"720p", "1080p"}:
                raise catalog.InvalidModelParametersError(
                    "Grok Upscale resolution must be 720p or 1080p"
                )

        if spec.id == "grok-video-1.5":
            images = clean.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 7:
                raise catalog.InvalidModelParametersError(
                    "Grok Imagine 1.5 accepts at most seven reference images"
                )
            nsfw = clean.get("nsfw_checker")
            if nsfw is not None and not isinstance(nsfw, bool):
                raise catalog.InvalidModelParametersError("Grok nsfw_checker must be boolean")

        if spec.id == "grok-video-extend":
            prompt = str(clean.get("prompt") or "").strip()
            if not prompt and clean.get("prompt") is None:
                raise catalog.InvalidModelParametersError("Grok Extend requires prompt")
            try:
                extend_at = int(clean.get("extend_at"))
            except (TypeError, ValueError) as exc:
                raise catalog.InvalidModelParametersError(
                    "Grok Extend extend_at must be an integer"
                ) from exc
            if extend_at < 2:
                raise catalog.InvalidModelParametersError(
                    "Grok Extend extend_at must be at least 2 seconds"
                )
            if str(clean.get("extend_times") or "") not in {"6", "10"}:
                raise catalog.InvalidModelParametersError(
                    "Grok Extend supports only 6 or 10 seconds"
                )

    catalog.ModelCatalog._validate_model_rules = audited_rules

    previous_normalize = video_contracts.normalize_kie_video_input

    def audited_normalize(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)

        if model in {
            "bytedance/seedance-2",
            "bytedance/seedance-2-fast",
            "bytedance/seedance-2-mini",
        }:
            return_last = source.get("return_last_frame", _MISSING)
            frame_mode = bool(source.get("first_frame_url") or source.get("last_frame_url"))
            reference_mode = bool(
                source.get("reference_image_urls")
                or source.get("reference_video_urls")
                or source.get("reference_audio_urls")
            )
            if frame_mode and reference_mode:
                raise video_contracts.KieVideoContractError(
                    "Seedance first/last-frame mode and multimodal reference mode are mutually exclusive"
                )
            if return_last is not _MISSING and not isinstance(return_last, bool):
                raise video_contracts.KieVideoContractError(
                    "Seedance return_last_frame must be boolean"
                )
            normalized = previous_normalize(model, source)
            # The legacy normalizer removes this documented field. Restore the
            # exact user value after its other validation has completed.
            if return_last is not _MISSING:
                normalized["return_last_frame"] = return_last
            return normalized

        if model in {"grok-imagine/text-to-video", "grok-imagine/image-to-video"}:
            mode = str(source.get("mode") or "normal")
            if mode not in {"fun", "normal", "spicy"}:
                raise video_contracts.KieVideoContractError("Unsupported Grok mode")
            resolution = str(source.get("resolution") or "480p")
            if resolution not in {"480p", "720p", "1080p"}:
                raise video_contracts.KieVideoContractError("Unsupported Grok resolution")
            ratio = str(source.get("aspect_ratio") or "16:9")
            if ratio not in {"2:3", "3:2", "1:1", "16:9", "9:16"}:
                raise video_contracts.KieVideoContractError("Unsupported Grok aspect ratio")
            try:
                _require_bool(source, "nsfw_checker")
            except ValueError as exc:
                raise video_contracts.KieVideoContractError(str(exc)) from exc

            if model == "grok-imagine/image-to-video":
                images = source.get("image_urls") or []
                task_id = str(source.get("task_id") or "").strip()
                if not isinstance(images, list) or len(images) > 1:
                    raise video_contracts.KieVideoContractError(
                        "Grok I2V accepts at most one external image"
                    )
                if images and task_id:
                    raise video_contracts.KieVideoContractError(
                        "Grok I2V accepts image_urls or task_id + index, not both"
                    )
                if not images and not task_id:
                    raise video_contracts.KieVideoContractError(
                        "Grok I2V requires image_urls or task_id + index"
                    )
                if task_id:
                    if source.get("index") in (None, ""):
                        raise video_contracts.KieVideoContractError(
                            "Grok I2V task_id requires index"
                        )
                    try:
                        index = int(source["index"])
                    except (TypeError, ValueError) as exc:
                        raise video_contracts.KieVideoContractError(
                            "Grok I2V index must be an integer"
                        ) from exc
                    if not 0 <= index <= 5:
                        raise video_contracts.KieVideoContractError(
                            "Grok I2V index must be between 0 and 5"
                        )
                    source["index"] = index
                if images and mode == "spicy":
                    raise video_contracts.KieVideoContractError(
                        "Grok I2V Spicy mode requires task_id + index"
                    )

        if model == "grok-imagine-video-1-5-preview":
            images = source.get("image_urls") or []
            if not isinstance(images, list) or len(images) > 7:
                raise video_contracts.KieVideoContractError(
                    "Grok Imagine 1.5 accepts at most seven reference images"
                )
            try:
                _require_bool(source, "nsfw_checker")
            except ValueError as exc:
                raise video_contracts.KieVideoContractError(str(exc)) from exc

        if model == "grok-imagine/upscale":
            resolution = str(source.get("resolution") or "1080p")
            if resolution not in {"720p", "1080p"}:
                raise video_contracts.KieVideoContractError(
                    "Grok Upscale resolution must be 720p or 1080p"
                )
            source["resolution"] = resolution

        if model == "grok-imagine/extend":
            task_id = str(source.get("task_id") or "").strip()
            if not task_id:
                raise video_contracts.KieVideoContractError("Grok Extend requires task_id")
            if "prompt" not in source:
                raise video_contracts.KieVideoContractError("Grok Extend requires prompt")
            try:
                extend_at = int(source.get("extend_at"))
            except (TypeError, ValueError) as exc:
                raise video_contracts.KieVideoContractError(
                    "Grok Extend extend_at must be an integer"
                ) from exc
            if extend_at < 2:
                raise video_contracts.KieVideoContractError(
                    "Grok Extend extend_at must be at least 2 seconds"
                )
            extend_times = str(source.get("extend_times") or "")
            if extend_times not in {"6", "10"}:
                raise video_contracts.KieVideoContractError(
                    "Grok Extend supports only 6 or 10 seconds"
                )
            # Existing compatibility normalizer internally expects an int but
            # restores the provider enum as string. Preserve that exact contract.
            source["extend_at"] = extend_at
            source["extend_times"] = extend_times

        normalized = previous_normalize(model, source)

        if model == "grok-imagine/upscale":
            normalized["resolution"] = str(source.get("resolution") or "1080p")
        if model == "grok-imagine/extend":
            normalized["extend_at"] = int(source["extend_at"])
            normalized["extend_times"] = str(source["extend_times"])
        return normalized

    video_contracts.normalize_kie_video_input = audited_normalize
