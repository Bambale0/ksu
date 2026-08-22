from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

_INSTALLED = False
_UNSET = object()


def _replace_spec(
    spec: Any,
    *,
    add_fields: tuple[str, ...] = (),
    remove_fields: tuple[str, ...] = (),
    required_add: tuple[str, ...] = (),
    required_remove: tuple[str, ...] = (),
    duration_field: str | None | object = _UNSET,
    min_seconds: int | None | object = _UNSET,
    max_seconds: int | None | object = _UNSET,
) -> Any:
    known = [field for field in spec.known_fields if field not in set(remove_fields)]
    for field in add_fields:
        if field not in known:
            known.append(field)

    required = [field for field in spec.required_fields if field not in set(required_remove)]
    for field in required_add:
        if field not in required:
            required.append(field)

    changes: dict[str, Any] = {
        "known_fields": tuple(known),
        "required_fields": tuple(required),
    }
    if duration_field is not _UNSET:
        changes["duration_field"] = duration_field
    if min_seconds is not _UNSET:
        changes["min_seconds"] = min_seconds
    if max_seconds is not _UNSET:
        changes["max_seconds"] = max_seconds
    return replace(spec, **changes)


def install_provider_contract_sync() -> None:
    """Keep ROXY's public controls and provider payloads on the same Kie contract.

    Kie model contracts evolve independently from ROXY releases.  This module is a
    single compatibility layer that is imported for every app/worker process so a
    UI option can never be silently discarded before submission.  It intentionally
    patches the existing registries instead of adding a third copy of model specs.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_video_contracts as video_contracts
    from app.services import model_catalog as catalog
    from app.services import model_ui as model_ui
    from app.services import model_ui_contract as ui_contract
    from app.services import music_generation as music

    replacements: dict[str, dict[str, Any]] = {
        # Kie uses `ratio` for Wan 2.7 T2V. Exposing both ratio + aspect_ratio
        # made the user's aspect-ratio choice a placebo because ratio had a default.
        "wan-2.7-t2v": {"remove_fields": ("aspect_ratio",)},
        # Provider duration=0 means auto. ROXY bills by the source/output seconds,
        # so the public form must ask for billing_seconds instead of a fake duration.
        "wan-2.7-video-edit": {
            "remove_fields": ("duration",),
            "duration_field": None,
        },
        # Current Seedream 5 Lite schemas expose output_format for both modes.
        "seedream-5-lite-t2i": {"add_fields": ("output_format",)},
        "seedream-5-lite-i2i": {"add_fields": ("output_format",)},
    }

    patched_specs = []
    for spec in catalog.SPECS:
        options = replacements.get(spec.id)
        patched_specs.append(_replace_spec(spec, **options) if options else spec)
    catalog.SPECS = tuple(patched_specs)
    catalog.ModelCatalog._by_id = {spec.id: spec for spec in catalog.SPECS}

    # Model-specific UI values. Keep the provider spelling/case exactly as sent.
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedream-5-lite-t2i", {})[
        "output_format"
    ] = ["png", "jpeg"]
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedream-5-lite-i2i", {})[
        "output_format"
    ] = ["png", "jpeg"]
    ui_contract.MODEL_DEFAULTS.setdefault("seedream-5-lite-t2i", {})[
        "output_format"
    ] = "png"
    ui_contract.MODEL_DEFAULTS.setdefault("seedream-5-lite-i2i", {})[
        "output_format"
    ] = "png"

    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("veo-3.1", {})[
        "aspect_ratio"
    ] = ["16:9", "9:16", "auto"]

    # Current Seedance 2 / Fast docs do not advertise adaptive; old saved drafts
    # are still normalized at the provider boundary for backwards compatibility.
    for model_id in ("seedance-2.0", "seedance-2.0-fast"):
        ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault(model_id, {})[
            "aspect_ratio"
        ] = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["aspect_ratio"] = "16:9"

    # Seedance 2.5 provider accepts 1080p. Keep upload limits aligned with Kie.
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedance-2.5", {})[
        "resolution"
    ] = ["480p", "720p", "1080p"]
    ui_contract.MODEL_FIELD_OVERRIDES.setdefault("seedance-2.5", {}).setdefault(
        "reference_video_urls", {}
    )["max_size_mb"] = 200

    # Wan R2V reference_image/reference_video are arrays in the provider request.
    wan_r2v = ui_contract.MODEL_FIELD_OVERRIDES.setdefault("wan-2.7-r2v", {})
    wan_r2v["reference_image"] = {
        "control": "files",
        "label": "Референс-изображения",
        "max_items": 16,
    }
    wan_r2v["reference_video"] = {
        "control": "files",
        "label": "Референс-видео",
        "max_items": 16,
    }

    # Grok Extend uses a numeric extension point. `start/end` was an old generic
    # UI assumption and produced a provider-contract validation error.
    model_ui.FIELD_DEFINITIONS["extend_at"] = {
        "label": "Точка расширения",
        "control": "number",
        "group": "output",
        "min": 0,
        "max": 600,
        "step": 1,
        "suffix": "с",
    }

    # Video Edit should expose an explicit billing duration even though provider
    # duration itself is fixed to 0/auto.
    model_ui.MODEL_OVERRIDES.setdefault("wan-2.7-video-edit", {})[
        "billing_seconds"
    ] = {
        "label": "Оплачиваемая длительность видео",
        "min": 1,
        "max": 60,
        "required": True,
    }

    original_video_normalizer = video_contracts.normalize_kie_video_input
    original_veo_normalizer = video_contracts.normalize_kie_veo_input

    def normalize_video(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        if model == "wan/2-7-videoedit" and source.get("duration") in (None, ""):
            source["duration"] = 0

        preserved_seedance: dict[str, Any] = {}
        if model in video_contracts.SEEDANCE_20_MODELS:
            for field in ("return_last_frame", "fixed_lens"):
                if field in source:
                    value = source[field]
                    if value is not None and not isinstance(value, bool):
                        raise video_contracts.KieVideoContractError(f"{field} must be boolean")
                    preserved_seedance[field] = value

            frame_mode = bool(source.get("first_frame_url") or source.get("last_frame_url"))
            reference_mode = bool(
                source.get("reference_image_urls")
                or source.get("reference_video_urls")
                or source.get("reference_audio_urls")
            )
            if frame_mode and reference_mode:
                raise video_contracts.KieVideoContractError(
                    "Seedance frame mode and multimodal reference mode are mutually exclusive"
                )

        normalized = original_video_normalizer(model, source)
        # The previous compatibility normalizer removed documented Seedance fields.
        # Restore them so a visible control is never silently discarded.
        normalized.update(preserved_seedance)
        return normalized

    def normalize_veo(input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        aspect = source.get("aspect_ratio")
        if isinstance(aspect, str) and aspect.lower() == "auto":
            source["aspect_ratio"] = "auto"
        return original_veo_normalizer(source)

    video_contracts.normalize_kie_video_input = normalize_video
    video_contracts.normalize_kie_veo_input = normalize_veo

    # ModelCatalog had a temporary Seedance 2 hybrid bypass. Kie's current docs
    # explicitly describe frame and multimodal-reference scenarios as exclusive.
    from app.services.generations import GenerationService

    GenerationService._seedance20_hybrid_references = staticmethod(
        lambda _model_id, _parameters: {}
    )

    original_music_prepare = music.MusicGenerationService.prepare

    @classmethod
    def prepare_music(
        cls: type[music.MusicGenerationService],
        parameters: dict[str, Any],
        prompt: str = "",
    ) -> tuple[dict[str, Any], Any]:
        raw = dict(parameters or {})
        text = str(raw.get("prompt") or prompt or "").strip()
        if not bool(raw.get("customMode", False)) and len(text) > 500:
            raise music.MusicGenerationError(
                "В простом режиме Suno промпт должен быть не длиннее 500 символов"
            )
        return original_music_prepare(parameters, prompt)

    music.MusicGenerationService.prepare = prepare_music
