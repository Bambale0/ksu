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
    assert _field("wan-2.7-image", "resolution")["suggestions"] == ["1K", "2K"]
    assert _field("wan-2.7-image-pro", "resolution")["suggestions"] == ["1K", "2K", "4K"]
    assert _field("grok-video-i2v", "resolution")["suggestions"] == ["480p", "720p", "1080p"]
    assert _field("grok-video-t2v", "resolution")["suggestions"] == ["480p", "720p", "1080p"]
    assert _field("seedance-2.5", "resolution")["suggestions"] == ["480p", "720p", "1080p"]


def test_prompt_is_always_present_in_provider_payload() -> None:
    generation = SimpleNamespace(
        parameters={"_model_id": "nano-banana-2", "resolution": "1K"},
        prompt="пикачу",
        input_url=None,
    )

    payload = GenerationProviderService._input_for(generation)

    assert payload["prompt"] == "пикачу"
    assert payload["resolution"] == "1K"
    assert "_model_id" not in payload
