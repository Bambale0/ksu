from __future__ import annotations

from typing import Any

import pytest

from app.services.kie_image_contracts import normalize_kie_image_input
from app.services.kie_video_contracts import normalize_kie_veo_input, normalize_kie_video_input
from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.music_generation import MUSIC_MODEL_ID, MusicGenerationError, MusicGenerationService
from app.services.trending_model_catalog import ACTIVE_NEW_WORK_MODEL_IDS


IMAGE_LIST_FIELDS = {
    "image_urls",
    "input_urls",
    "image_input",
    "reference_image_urls",
    "reference_image",
}
IMAGE_SINGLE_FIELDS = {"image_url", "first_frame_url", "last_frame_url", "first_frame"}
VIDEO_LIST_FIELDS = {"video_urls", "reference_video_urls", "reference_video"}
VIDEO_SINGLE_FIELDS = {"video_url", "first_clip_url"}
AUDIO_LIST_FIELDS = {"reference_audio_urls"}
AUDIO_SINGLE_FIELDS = {"audio_url", "driving_audio_url", "reference_voice"}


def _registered_models() -> list[dict[str, Any]]:
    """Return every provider spec, including hidden/history-compatible routes."""
    return [
        spec.public_dict()
        for _model_id, spec in sorted(ModelCatalog._by_id.items())
    ]


REGISTERED_MODELS = _registered_models()


def _field(schema: dict[str, Any], name: str) -> dict[str, Any] | None:
    return next((item for item in schema.get("fields", []) if item.get("name") == name), None)


def _default_value(model: dict[str, Any], schema: dict[str, Any], name: str) -> Any:
    defaults = schema.get("defaults", {})
    if name in defaults:
        return defaults[name]
    field = _field(schema, name) or {}
    suggestions = field.get("suggestions") or []
    if suggestions:
        return suggestions[0]
    if name == "prompt":
        return "Golden contract test"
    if name in IMAGE_LIST_FIELDS:
        return ["https://example.com/reference.jpg"]
    if name in IMAGE_SINGLE_FIELDS:
        return "https://example.com/reference.jpg"
    if name in VIDEO_LIST_FIELDS:
        return ["https://example.com/reference.mp4"]
    if name in VIDEO_SINGLE_FIELDS:
        return "https://example.com/reference.mp4"
    if name in AUDIO_LIST_FIELDS:
        return ["https://example.com/reference.wav"]
    if name in AUDIO_SINGLE_FIELDS:
        return "https://example.com/reference.wav"
    if name == "task_id":
        return "task_golden"
    if name == "index":
        return 0
    if name == "extend_at":
        return 2
    if name == "extend_times":
        return "6"
    if name == "mode":
        return "normal"
    if field.get("control") == "toggle":
        return False
    if field.get("control") == "number":
        return field.get("min") if field.get("min") is not None else 1
    return "golden"


def _minimal(model: dict[str, Any]) -> tuple[dict[str, Any], int | None]:
    schema = build_public_model_ui_schema(model)
    known_fields = set(model["known_fields"])
    clean = {
        key: value
        for key, value in dict(schema.get("defaults", {})).items()
        if key in known_fields
    }
    for name in model["required_fields"]:
        if clean.get(name) in (None, "", []):
            clean[name] = _default_value(model, schema, name)
    if "prompt" in known_fields and not clean.get("prompt"):
        clean["prompt"] = "Golden contract test"

    model_id = model["id"]
    if model_id == "wan-2.7-i2v":
        clean["first_frame_url"] = "https://example.com/first.jpg"
    elif model_id == "wan-2.7-r2v":
        clean["reference_image"] = ["https://example.com/reference.jpg"]
    elif model_id == "grok-video-i2v":
        clean["image_urls"] = ["https://example.com/reference.jpg"]
        clean.pop("task_id", None)
        clean.pop("index", None)
    elif model_id == "grok-video-extend":
        clean.update(
            {
                "task_id": "task_golden",
                "prompt": "Continue",
                "extend_at": 2,
                "extend_times": "6",
            }
        )
    elif model_id == "grok-video-upscale":
        clean["task_id"] = "task_golden"
    elif model_id.startswith("kling-motion-"):
        clean.update(
            {
                "prompt": "Follow the motion",
                "input_urls": ["https://example.com/reference.jpg"],
                "video_urls": ["https://example.com/motion.mp4"],
            }
        )

    if "duration" in known_fields and clean.get("duration") in (None, "", 0, "0"):
        duration = _field(schema, "duration") or {}
        suggestions = duration.get("suggestions") or []
        clean["duration"] = next(
            (value for value in suggestions if int(value) > 0),
            model.get("min_seconds") or 1,
        )

    billing = schema.get("billing_seconds") or {}
    billing_seconds = None
    if billing.get("required"):
        billing_seconds = int(billing.get("min") or model.get("min_seconds") or 1)
    if model_id == "grok-video-upscale":
        billing_seconds = 6
    return clean, billing_seconds


def _normalize_provider_payload(model: dict[str, Any], clean: dict[str, Any]) -> dict[str, Any]:
    spec = ModelCatalog.get(model["id"])
    if spec.media_type == "image":
        return normalize_kie_image_input(spec.kie_model, clean)
    if spec.id == "veo-3.1":
        return normalize_kie_veo_input(clean)
    return normalize_kie_video_input(spec.kie_model, clean)


def test_registry_has_43_golden_payload_entries_including_music() -> None:
    assert len(ModelCatalog.list()) == 23  # customer-visible products
    assert len(REGISTERED_MODELS) == 42  # provider/history/auto-route registry
    assert MUSIC_MODEL_ID == "suno-v5.5"
    assert len(REGISTERED_MODELS) + 1 == 43


@pytest.mark.parametrize("model", REGISTERED_MODELS, ids=lambda item: item["id"])
def test_every_registered_model_has_a_normalizable_golden_payload(model: dict[str, Any]) -> None:
    schema = build_public_model_ui_schema(model)
    fields = {item["name"] for item in schema.get("fields", [])}
    assert fields == set(model["known_fields"])

    parameters, billing_seconds = _minimal(model)
    spec = ModelCatalog.get(model["id"])

    if model["id"] in ACTIVE_NEW_WORK_MODEL_IDS:
        prepared_spec, clean, cost, seconds, _unit = ModelCatalog.prepare(
            model["id"],
            parameters,
            billing_seconds=billing_seconds,
        )
        assert prepared_spec.id == spec.id
        assert cost > 0
        if spec.price_mode == "per_second":
            assert seconds is not None and seconds > 0
    else:
        # Historical specs remain registered so existing generation rows can be
        # replayed/rendered. They are not admitted for new customer work, but their
        # provider payload contract must still stay valid for recovery/reconciliation.
        clean = dict(parameters)
        for required in spec.required_fields:
            assert clean.get(required) not in (None, "", []), (spec.id, required)
        ModelCatalog._validate_model_rules(spec, clean)

    normalized = _normalize_provider_payload(model, clean)

    # A value exposed by the schema and accepted by the model contract must reach
    # the provider boundary instead of being silently discarded.
    assert set(clean) <= set(normalized), (model["id"], set(clean) - set(normalized))


def test_suno_has_a_golden_payload_entry() -> None:
    clean, cost = MusicGenerationService.prepare(
        {
            "prompt": "Golden music contract",
            "customMode": False,
            "instrumental": False,
        }
    )
    assert clean == {
        "prompt": "Golden music contract",
        "customMode": False,
        "instrumental": False,
    }
    assert cost > 0


def test_p0_contract_regressions_are_locked() -> None:
    models = {item["id"]: item for item in REGISTERED_MODELS}

    wan_t2v = models["wan-2.7-t2v"]
    assert "ratio" in wan_t2v["known_fields"]
    assert "aspect_ratio" not in wan_t2v["known_fields"]

    wan_edit = build_public_model_ui_schema(models["wan-2.7-video-edit"])
    duration = _field(wan_edit, "duration")
    assert duration and duration["suggestions"] == [0, *range(2, 11)]
    assert wan_edit["defaults"]["duration"] == 5
    assert wan_edit["billing_seconds"]["required"] is False

    grok_extend = build_public_model_ui_schema(models["grok-video-extend"])
    assert _field(grok_extend, "extend_at")["control"] == "number"
    assert _field(grok_extend, "extend_at")["min"] == 2
    assert _field(grok_extend, "extend_times")["suggestions"] == ["6", "10"]
    assert "billing_seconds" not in grok_extend

    veo = build_public_model_ui_schema(models["veo-3.1"])
    assert _field(veo, "aspect_ratio")["suggestions"] == ["16:9", "9:16", "auto"]
    assert normalize_kie_veo_input({"prompt": "x", "aspect_ratio": "auto"})[
        "aspect_ratio"
    ] == "auto"

    with pytest.raises(MusicGenerationError):
        MusicGenerationService.prepare({"prompt": "x" * 501})
    clean, _price = MusicGenerationService.prepare({"prompt": "x" * 500})
    assert len(clean["prompt"]) == 500


def test_p1_provider_capabilities_are_exposed_without_placebo_fields() -> None:
    models = {item["id"]: item for item in REGISTERED_MODELS}

    seedance = build_public_model_ui_schema(models["seedance-2.0"])
    assert _field(seedance, "resolution")["suggestions"] == ["480p", "720p", "1080p", "4K"]
    assert "adaptive" not in _field(seedance, "aspect_ratio")["suggestions"]
    assert _field(seedance, "fixed_lens") is None
    assert _field(seedance, "return_last_frame") is None
    assert _field(seedance, "nsfw_checker") is not None

    seedance25 = build_public_model_ui_schema(models["seedance-2.5"])
    assert "1080p" in _field(seedance25, "resolution")["suggestions"]
    assert _field(seedance25, "reference_video_urls")["max_size_mb"] == 200
    assert _field(seedance25, "duration")["suggestions"] == list(range(4, 31))

    wan_image = build_public_model_ui_schema(models["wan-2.7-image"])
    for name in ("aspect_ratio", "color_palette", "nsfw_checker"):
        assert _field(wan_image, name) is not None

    wan_r2v = build_public_model_ui_schema(models["wan-2.7-r2v"])
    assert _field(wan_r2v, "reference_image")["control"] == "files"
    assert _field(wan_r2v, "reference_video")["control"] == "files"
    assert _field(wan_r2v, "reference_image")["max_items"] == 5
    assert _field(wan_r2v, "reference_video")["max_items"] == 5

    seedream_lite = build_public_model_ui_schema(models["seedream-5-lite-t2i"])
    assert _field(seedream_lite, "output_format")["suggestions"] == ["png", "jpeg"]

    grok_t2v = build_public_model_ui_schema(models["grok-video-t2v"])
    assert _field(grok_t2v, "mode")["suggestions"] == ["fun", "normal", "spicy"]
    assert _field(grok_t2v, "resolution")["suggestions"] == ["480p", "720p", "1080p"]
    assert _field(grok_t2v, "nsfw_checker") is not None

    grok_i2v = build_public_model_ui_schema(models["grok-video-i2v"])
    scenarios = {item["id"]: item for item in grok_i2v["scenario"]["items"]}
    assert scenarios["kie_task"]["required_fields"] == ["task_id", "index"]
    assert _field(grok_i2v, "index") is not None

    grok15 = build_public_model_ui_schema(models["grok-video-1.5"])
    assert _field(grok15, "resolution")["suggestions"] == ["480p", "720p", "1080p"]
    assert _field(grok15, "duration")["suggestions"] == list(range(1, 16))
    assert _field(grok15, "nsfw_checker") is not None

    grok_upscale = build_public_model_ui_schema(models["grok-video-upscale"])
    assert _field(grok_upscale, "resolution")["suggestions"] == ["720p", "1080p"]
