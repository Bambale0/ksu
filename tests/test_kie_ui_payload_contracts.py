from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.services.generation_provider import GenerationProviderService
from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


def _schema(model_id: str) -> dict[str, Any]:
    return build_public_model_ui_schema(ModelCatalog.get(model_id).public_dict())


def _field(model_id: str, name: str) -> dict[str, Any]:
    for field in _schema(model_id).get("fields", []):
        if field.get("name") == name:
            return field
    raise AssertionError(f"{model_id} has no UI field {name}")


def test_image_models_do_not_expose_video_resolutions() -> None:
    for model_id in (
        "nano-banana-pro",
        "nano-banana-2",
        "wan-2.7-image",
        "wan-2.7-image-pro",
    ):
        suggestions = set(_field(model_id, "resolution").get("suggestions") or [])
        assert not suggestions.intersection({"480p", "720p", "1080p"})


def test_resolution_options_are_model_specific() -> None:
    assert _field("nano-banana-2", "resolution")["suggestions"] == ["1K", "2K", "4K"]
    assert _field("nano-banana-pro", "resolution")["suggestions"] == ["1K", "2K", "4K"]
    assert _field("gpt-image-2-t2i", "resolution")["suggestions"] == ["1K", "2K", "4K"]
    assert _field("gpt-image-2-i2i", "resolution")["suggestions"] == ["1K", "2K", "4K"]
    assert _field("wan-2.7-image", "resolution")["suggestions"] == ["1K", "2K"]
    assert _field("wan-2.7-image-pro", "resolution")["suggestions"] == ["1K", "2K", "4K"]
    assert _field("grok-video-i2v", "resolution")["suggestions"] == ["480p", "720p", "1080p"]
    assert _field("grok-video-t2v", "resolution")["suggestions"] == ["480p", "720p", "1080p"]
    assert _field("seedance-2.0", "resolution")["suggestions"] == ["480p", "720p", "1080p"]
    assert _field("seedance-2.5", "resolution")["suggestions"] == ["480p", "720p", "1080p"]


def test_current_image_upload_limits_are_exposed_to_dynamic_ui() -> None:
    expected = {
        ("nano-banana-edit", "image_urls"): (10, 10),
        ("nano-banana-pro", "image_input"): (8, 30),
        ("nano-banana-2", "image_input"): (14, 30),
        ("nano-banana-2-lite", "image_urls"): (10, 30),
        ("seedream-4.5-edit", "image_urls"): (14, 10),
        ("seedream-5-lite-i2i", "image_urls"): (14, 30),
        ("seedream-5-pro-i2i", "image_urls"): (10, 10),
        ("gpt-image-1.5-i2i", "input_urls"): (16, 10),
        ("gpt-image-2-i2i", "input_urls"): (16, 30),
        ("grok-image-i2i", "image_urls"): (1, 10),
    }
    for (model_id, field_name), (max_items, max_size_mb) in expected.items():
        field = _field(model_id, field_name)
        assert field["max_items"] == max_items, model_id
        assert field["max_size_mb"] == max_size_mb, model_id


def test_nano_banana_public_contract_exposes_provider_nsfw_toggle() -> None:
    for model_id in ("nano-banana", "nano-banana-edit"):
        field = _field(model_id, "nsfw_checker")
        assert field["control"] == "toggle"
        assert _schema(model_id)["defaults"]["nsfw_checker"] is True


def test_prompt_is_always_present_in_provider_payload() -> None:
    generation = SimpleNamespace(
        parameters={"_model_id": "nano-banana-2", "resolution": "1K"},
        prompt="пикачу",
        input_url=None,
        action_type=None,
    )

    payload = GenerationProviderService._input_for(generation)

    assert payload["prompt"] == "пикачу"
    assert payload["resolution"] == "1K"
    assert "_model_id" not in payload
