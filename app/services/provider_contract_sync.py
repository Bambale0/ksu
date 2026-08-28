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
    """Synchronize public ROXY controls with the current Kie request contracts.

    Kie changes individual model schemas independently. This compatibility layer is
    installed before API/worker modules import their service functions, so the model
    catalog, public ui_schema, billing and final provider normalizers stay aligned.
    Old saved drafts remain normalized at the provider boundary, while new UI never
    exposes a field that will be silently discarded.
    """

    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    from app.services import kie_video_contracts as video_contracts
    from app.services import model_catalog as catalog
    from app.services import model_routing as routing
    from app.services import model_ui as model_ui
    from app.services import model_ui_contract as ui_contract
    from app.services import music_generation as music

    replacements: dict[str, dict[str, Any]] = {
        # Wan Image current Kie schema.
        "wan-2.7-image": {"add_fields": ("aspect_ratio", "color_palette", "nsfw_checker")},
        "wan-2.7-image-pro": {"add_fields": ("aspect_ratio", "color_palette", "nsfw_checker")},
        # Kie T2V calls the ratio field `ratio`; `aspect_ratio` is not part of this endpoint.
        "wan-2.7-t2v": {
            "remove_fields": ("aspect_ratio",),
            "add_fields": ("nsfw_checker",),
        },
        # I2V has no aspect_ratio field in Kie's current schema.
        "wan-2.7-i2v": {
            "remove_fields": ("aspect_ratio",),
            "add_fields": ("nsfw_checker",),
        },
        "wan-2.7-video-edit": {"add_fields": ("nsfw_checker",)},
        "wan-2.7-r2v": {
            "add_fields": ("nsfw_checker",),
            "min_seconds": 2,
            "max_seconds": 10,
        },
        # Current Seedream 5 Lite exposes output_format in both modes.
        "seedream-5-lite-t2i": {"add_fields": ("output_format",)},
        "seedream-5-lite-i2i": {"add_fields": ("output_format",)},
        # Current Seedance 2/2 Fast/Mini expose nsfw_checker but no legacy
        # fixed_lens or return_last_frame request keys.
        "seedance-2.0": {
            "remove_fields": ("fixed_lens", "return_last_frame"),
            "add_fields": ("nsfw_checker",),
            "min_seconds": 4,
            "max_seconds": 15,
        },
        "seedance-2.0-fast": {
            "remove_fields": ("fixed_lens", "return_last_frame"),
            "add_fields": ("nsfw_checker",),
            "min_seconds": 4,
            "max_seconds": 15,
        },
        "seedance-2.0-mini": {
            "remove_fields": ("fixed_lens", "return_last_frame"),
            "add_fields": ("nsfw_checker",),
            "min_seconds": 4,
            "max_seconds": 15,
        },
        # Grok current schemas.
        "grok-image-t2i": {"add_fields": ("enable_pro", "nsfw_checker")},
        "grok-image-i2i": {"add_fields": ("nsfw_checker",)},
        "grok-video-t2v": {"add_fields": ("nsfw_checker",)},
        "grok-video-i2v": {
            "add_fields": ("index", "nsfw_checker"),
            "required_remove": ("image_urls",),
        },
        "grok-video-1.5": {
            "add_fields": ("nsfw_checker",),
            "max_seconds": 15,
        },
        "grok-video-upscale": {"add_fields": ("resolution",)},
        "grok-video-extend": {
            "required_add": ("prompt", "extend_at", "extend_times"),
            "duration_field": "extend_times",
            "min_seconds": 6,
            "max_seconds": 10,
        },
    }

    patched_specs = []
    for spec in catalog.SPECS:
        options = replacements.get(spec.id)
        patched_specs.append(_replace_spec(spec, **options) if options else spec)
    catalog.SPECS = tuple(patched_specs)
    catalog.ModelCatalog._by_id = {spec.id: spec for spec in catalog.SPECS}

    # Generic definitions for newly exposed provider fields.
    model_ui.FIELD_DEFINITIONS["color_palette"] = {
        "label": "Цветовая палитра",
        "control": "text",
        "group": "advanced",
        "placeholder": "Например: #FF5AB8 40%, #8F55FF 35%, #0B0B10 25%",
    }
    model_ui.FIELD_DEFINITIONS["enable_pro"] = {
        "label": "Pro-качество",
        "control": "toggle",
        "group": "output",
    }
    model_ui.FIELD_DEFINITIONS["index"] = {
        "label": "Индекс изображения",
        "control": "number",
        "group": "references",
        "min": 0,
        "max": 5,
        "step": 1,
    }
    model_ui.FIELD_DEFINITIONS["extend_at"] = {
        "label": "Начать расширение с",
        "control": "number",
        "group": "output",
        "min": 2,
        "max": 600,
        "step": 1,
        "suffix": "с",
    }

    # Model-specific UI values. Provider spelling/case is kept exactly as sent.
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedream-5-lite-t2i", {})[
        "output_format"
    ] = ["png", "jpeg"]
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedream-5-lite-i2i", {})[
        "output_format"
    ] = ["png", "jpeg"]
    ui_contract.MODEL_DEFAULTS.setdefault("seedream-5-lite-t2i", {})["output_format"] = "png"
    ui_contract.MODEL_DEFAULTS.setdefault("seedream-5-lite-i2i", {})["output_format"] = "png"

    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("veo-3.1", {})[
        "aspect_ratio"
    ] = ["16:9", "9:16", "auto"]

    seedance_ratios = ["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"]
    for model_id in ("seedance-2.0", "seedance-2.0-fast"):
        ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault(model_id, {})["aspect_ratio"] = seedance_ratios
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["aspect_ratio"] = "16:9"
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["nsfw_checker"] = True
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedance-2.0", {})[
        "resolution"
    ] = ["480p", "720p", "1080p"]
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedance-2.0-fast", {})[
        "resolution"
    ] = ["480p", "720p"]
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedance-2.0-mini", {})[
        "resolution"
    ] = ["480p", "720p"]
    ui_contract.MODEL_DEFAULTS.setdefault("seedance-2.0-mini", {})["nsfw_checker"] = True

    # Full documented integer ranges instead of example-only 5/10/15 choices.
    for model_id in ("seedance-2.0", "seedance-2.0-fast", "seedance-2.0-mini"):
        ui_contract.KIE_DURATION_OPTIONS[model_id] = list(range(4, 16))
    ui_contract.KIE_DURATION_OPTIONS["seedance-2.5"] = list(range(4, 31))

    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("seedance-2.5", {})[
        "resolution"
    ] = ["480p", "720p", "1080p"]
    ui_contract.MODEL_FIELD_OVERRIDES.setdefault("seedance-2.5", {}).setdefault(
        "reference_video_urls", {}
    )["max_size_mb"] = 200

    # Wan current controls and limits.
    for model_id in ("wan-2.7-image", "wan-2.7-image-pro"):
        ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault(model_id, {})[
            "aspect_ratio"
        ] = ui_contract.WAN_IMAGE_RATIOS
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["aspect_ratio"] = "1:1"
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["nsfw_checker"] = True
    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("wan-2.7-t2v", {})[
        "ratio"
    ] = ["16:9", "9:16", "1:1", "4:3", "3:4"]
    for model_id in ("wan-2.7-t2v", "wan-2.7-i2v", "wan-2.7-video-edit", "wan-2.7-r2v"):
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {})["nsfw_checker"] = True
    ui_contract.KIE_DURATION_OPTIONS["wan-2.7-video-edit"] = [0, *range(2, 11)]
    ui_contract.KIE_DURATION_OPTIONS["wan-2.7-r2v"] = list(range(2, 11))
    ui_contract.MODEL_DEFAULTS.setdefault("wan-2.7-video-edit", {})["duration"] = 5

    wan_r2v = ui_contract.MODEL_FIELD_OVERRIDES.setdefault("wan-2.7-r2v", {})
    wan_r2v["reference_image"] = {
        "control": "files",
        "label": "Референс-изображения",
        "max_items": 5,
        "max_size_mb": 30,
    }
    wan_r2v["reference_video"] = {
        "control": "files",
        "label": "Референс-видео",
        "max_items": 5,
        "max_size_mb": 10,
    }

    # Wan Video Edit duration=0 is supported, but billing then needs source length.
    # Keep normal duration selectable and offer an optional explicit source duration.
    model_ui.MODEL_OVERRIDES.setdefault("wan-2.7-video-edit", {})["billing_seconds"] = {
        "label": "Длительность исходного видео для Auto",
        "min": 1,
        "max": 600,
        "required": False,
    }

    # Grok families.
    grok_ratios = ["2:3", "3:2", "1:1", "16:9", "9:16"]
    for model_id in ("grok-video-t2v", "grok-video-i2v"):
        fields = ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault(model_id, {})
        fields["mode"] = ["fun", "normal", "spicy"]
        fields["resolution"] = ["480p", "720p", "1080p"]
        fields["aspect_ratio"] = grok_ratios
        ui_contract.MODEL_DEFAULTS.setdefault(model_id, {}).update(
            {"mode": "normal", "resolution": "480p", "aspect_ratio": "16:9", "nsfw_checker": True}
        )
        ui_contract.KIE_DURATION_OPTIONS[model_id] = list(range(1, 31))

    grok15 = ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("grok-video-1.5", {})
    grok15["aspect_ratio"] = ["auto", "1:1", "16:9", "9:16", "3:2", "2:3"]
    grok15["resolution"] = ["480p", "720p", "1080p"]
    ui_contract.MODEL_DEFAULTS.setdefault("grok-video-1.5", {}).update(
        {"aspect_ratio": "auto", "resolution": "480p", "duration": 8, "nsfw_checker": True}
    )
    ui_contract.KIE_DURATION_OPTIONS["grok-video-1.5"] = list(range(1, 16))
    ui_contract.MODEL_FIELD_OVERRIDES.setdefault("grok-video-1.5", {})[
        "image_urls"
    ] = {"max_items": 7, "max_size_mb": 20}

    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("grok-video-upscale", {})[
        "resolution"
    ] = ["720p", "1080p"]
    ui_contract.MODEL_DEFAULTS.setdefault("grok-video-upscale", {})[
        "resolution"
    ] = "1080p"

    ui_contract.MODEL_FIELD_SUGGESTIONS.setdefault("grok-video-extend", {})[
        "extend_times"
    ] = ["6", "10"]
    ui_contract.MODEL_DEFAULTS.setdefault("grok-video-extend", {})[
        "extend_times"
    ] = "6"
    ui_contract.MODEL_FIELD_OVERRIDES.setdefault("grok-video-extend", {})[
        "extend_times"
    ] = {"control": "combobox", "label": "Продлить на", "group": "output", "suffix": "с"}

    ui_contract.MODEL_DEFAULTS.setdefault("grok-image-t2i", {}).update(
        {"enable_pro": False, "nsfw_checker": True}
    )
    ui_contract.MODEL_DEFAULTS.setdefault("grok-image-i2i", {})["nsfw_checker"] = True

    # `task_id + index` is a real Grok I2V reference source even though it is not
    # an uploaded image URL. Keep automatic T2V/I2V product routing aware of it.
    original_select_model_id = routing._select_model_id

    def select_model_id(requested_model_id: str, parameters: dict[str, Any], input_url: str | None) -> str:
        if requested_model_id in {"grok-video-t2v", "grok-video-i2v"} and parameters.get("task_id"):
            return "grok-video-i2v"
        return original_select_model_id(requested_model_id, parameters, input_url)

    routing._select_model_id = select_model_id

    # Add provider-specific validation that cannot be expressed as simple required_fields.
    original_model_rules = catalog.ModelCatalog._validate_model_rules

    @staticmethod
    def validate_model_rules(spec: Any, clean: dict[str, Any]) -> None:
        original_model_rules(spec, clean)
        if spec.id == "grok-video-i2v":
            images = clean.get("image_urls") or []
            task_id = str(clean.get("task_id") or "").strip()
            if images and task_id:
                raise catalog.InvalidModelParametersError(
                    "Grok I2V accepts image_urls or task_id + index, not both"
                )
            if not images and not task_id:
                raise catalog.InvalidModelParametersError(
                    "Grok I2V requires an uploaded image or task_id + index"
                )
            if task_id and clean.get("index") in (None, ""):
                raise catalog.InvalidModelParametersError("Grok I2V task_id requires index")
            if images and str(clean.get("mode") or "normal") == "spicy":
                raise catalog.InvalidModelParametersError(
                    "Grok I2V Spicy mode is available only with task_id + index"
                )
        if spec.id == "grok-video-extend":
            if str(clean.get("extend_times") or "") not in {"6", "10"}:
                raise catalog.InvalidModelParametersError("Grok Extend supports only 6 or 10 seconds")
            try:
                extend_at = int(clean.get("extend_at"))
            except (TypeError, ValueError) as exc:
                raise catalog.InvalidModelParametersError("Grok Extend extend_at must be an integer") from exc
            if extend_at < 2:
                raise catalog.InvalidModelParametersError("Grok Extend extend_at must be at least 2 seconds")
        if spec.id == "wan-2.7-r2v":
            images = clean.get("reference_image") or []
            videos = clean.get("reference_video") or []
            if not isinstance(images, list) or not isinstance(videos, list):
                raise catalog.InvalidModelParametersError("Wan R2V references must be arrays")
            if not images and not videos:
                raise catalog.InvalidModelParametersError("Wan R2V requires an image or video reference")
            if len(images) + len(videos) > 5:
                raise catalog.InvalidModelParametersError("Wan R2V accepts at most five image/video references")

    catalog.ModelCatalog._validate_model_rules = validate_model_rules

    original_video_normalizer = video_contracts.normalize_kie_video_input
    original_veo_normalizer = video_contracts.normalize_kie_veo_input

    def normalize_video(model: str, input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        requested_resolution = str(source.get("resolution") or "")
        requested_mode = str(source.get("mode") or "")
        requested_extend_times = source.get("extend_times")

        # Old normalizer predates current Seedance 2 Standard high-resolution tiers.
        if model == "bytedance/seedance-2" and requested_resolution in {"1080p", "4K"}:
            source["resolution"] = "720p"

        # Old Grok normalizer allowed only normal mode; Kie now exposes fun/spicy too.
        if model in {"grok-imagine/text-to-video", "grok-imagine/image-to-video"}:
            if requested_mode and requested_mode not in {"fun", "normal", "spicy"}:
                raise video_contracts.KieVideoContractError("Unsupported Grok mode")
            if requested_mode in {"fun", "spicy"}:
                source["mode"] = "normal"
            resolution = str(source.get("resolution") or "480p")
            if resolution not in {"480p", "720p", "1080p"}:
                raise video_contracts.KieVideoContractError("Unsupported Grok resolution")

        if model == "grok-imagine-video-1-5-preview":
            resolution = str(source.get("resolution") or "480p")
            aspect = str(source.get("aspect_ratio") or "auto")
            if resolution not in {"480p", "720p", "1080p"}:
                raise video_contracts.KieVideoContractError("Unsupported Grok 1.5 resolution")
            if aspect not in {"auto", "1:1", "16:9", "9:16", "3:2", "2:3"}:
                raise video_contracts.KieVideoContractError("Unsupported Grok 1.5 aspect ratio")

        if model == "grok-imagine/extend" and requested_extend_times not in (None, ""):
            if str(requested_extend_times) not in {"6", "10"}:
                raise video_contracts.KieVideoContractError("Grok Extend supports only 6 or 10 seconds")
            # Legacy normalizer coerces to int; Kie's current schema expects string enum.
            source["extend_times"] = int(str(requested_extend_times))

        normalized = original_video_normalizer(model, source)

        if model == "bytedance/seedance-2" and requested_resolution in {"1080p", "4K"}:
            normalized["resolution"] = requested_resolution
        if model in {"grok-imagine/text-to-video", "grok-imagine/image-to-video"} and requested_mode in {"fun", "spicy"}:
            normalized["mode"] = requested_mode
        if model == "grok-imagine/extend" and requested_extend_times not in (None, ""):
            normalized["extend_times"] = str(requested_extend_times)
        return normalized

    def normalize_veo(input_data: dict[str, Any]) -> dict[str, Any]:
        source = deepcopy(input_data)
        aspect = source.get("aspect_ratio")
        if isinstance(aspect, str) and aspect.lower() == "auto":
            source["aspect_ratio"] = "auto"
        return original_veo_normalizer(source)

    video_contracts.normalize_kie_video_input = normalize_video
    video_contracts.normalize_kie_veo_input = normalize_veo

    # Kie's current Seedance scenarios are exclusive; remove the temporary hybrid bypass.
    from app.services.generations import GenerationService

    GenerationService._seedance20_hybrid_references = staticmethod(
        lambda _model_id, _parameters: {}
    )

    # Public schema post-processing for conditional/provider-specific modes.
    original_public_schema = ui_contract.build_public_model_ui_schema

    def build_public_schema(model: dict[str, Any]) -> dict[str, Any]:
        schema = original_public_schema(model)
        model_id = str(model.get("id") or "")
        if model_id == "grok-video-extend":
            schema.pop("billing_seconds", None)
        if model_id == "grok-video-i2v":
            schema["scenario"] = {
                "default": "external_image",
                "items": [
                    {
                        "id": "external_image",
                        "title": "Загрузить изображение",
                        "visible_fields": ["image_urls"],
                        "clear_fields": ["task_id", "index"],
                        "required_fields": ["image_urls"],
                    },
                    {
                        "id": "kie_task",
                        "title": "Из Grok-задачи",
                        "visible_fields": ["task_id", "index"],
                        "clear_fields": ["image_urls"],
                        "required_fields": ["task_id", "index"],
                    },
                ],
            }
        return schema

    ui_contract.build_public_model_ui_schema = build_public_schema

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
