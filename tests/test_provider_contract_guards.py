from __future__ import annotations

import pytest

from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


def _field(schema: dict, name: str) -> dict | None:
    return next((field for field in schema.get("fields", []) if field.get("name") == name), None)


def test_wan_video_edit_audio_setting_is_a_real_provider_control() -> None:
    model = next(item for item in ModelCatalog.list() if item["id"] == "wan-2.7-video-edit")
    schema = build_public_model_ui_schema(model)
    audio = _field(schema, "audio_setting")
    assert audio is not None
    assert audio["control"] == "combobox"
    assert audio["suggestions"] == ["auto", "origin"]
    assert schema["defaults"]["audio_setting"] == "auto"


def test_wan_thinking_mode_with_references_is_rejected_instead_of_silently_disabled() -> None:
    with pytest.raises(InvalidModelParametersError, match="thinking_mode"):
        ModelCatalog.prepare(
            "wan-2.7-image",
            {
                "prompt": "portrait",
                "input_urls": ["https://example.com/ref.jpg"],
                "aspect_ratio": "1:1",
                "resolution": "1K",
                "n": 1,
                "thinking_mode": True,
            },
        )


def test_wan_pro_4k_edit_is_rejected_instead_of_silently_downgraded() -> None:
    with pytest.raises(InvalidModelParametersError, match="4K"):
        ModelCatalog.prepare(
            "wan-2.7-image-pro",
            {
                "prompt": "edit portrait",
                "input_urls": ["https://example.com/ref.jpg"],
                "aspect_ratio": "1:1",
                "resolution": "4K",
                "n": 1,
                "thinking_mode": False,
            },
        )


def test_removed_provider_fields_cannot_survive_as_hidden_defaults() -> None:
    for model_id in ("seedance-2.0", "seedance-2.0-fast", "seedance-2.0-mini"):
        model = next(item for item in ModelCatalog.list() if item["id"] == model_id)
        schema = build_public_model_ui_schema(model)
        fields = {field["name"] for field in schema["fields"]}
        assert "fixed_lens" not in fields
        assert "return_last_frame" not in fields
        assert set(schema.get("defaults", {})) <= fields
