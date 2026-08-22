from __future__ import annotations

import pytest

from app.services.kie_video_contracts import KieVideoContractError, normalize_kie_veo_input, normalize_kie_video_input
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


def test_kling_public_schema_no_longer_forces_aspect_ratio_for_frame_mode() -> None:
    schema = build_public_model_ui_schema(ModelCatalog.get("kling-3.0").public_dict())
    fields = {field["name"]: field for field in schema["fields"]}
    assert "default" not in fields["aspect_ratio"]


def test_kling_frame_mode_rejects_explicit_aspect_ratio_before_provider() -> None:
    base = {
        "prompt": "a cinematic reveal",
        "image_urls": ["https://cdn.example/first.png"],
        "duration": 5,
        "mode": "std",
    }
    spec, clean, _cost, _seconds, _unit = ModelCatalog.prepare("kling-3.0", base)
    payload = normalize_kie_video_input(spec.kie_model, clean)
    assert "aspect_ratio" not in payload

    with pytest.raises(InvalidModelParametersError, match="must be omitted"):
        ModelCatalog.prepare("kling-3.0", {**base, "aspect_ratio": "16:9"})
    with pytest.raises(KieVideoContractError, match="must be omitted"):
        normalize_kie_video_input(
            "kling-3.0/video", {**base, "aspect_ratio": "16:9"}
        )


def test_kling_multishot_uses_storyboard_cap_not_stale_sum_equality() -> None:
    valid = {
        "prompt": "multi scene campaign",
        "duration": 5,
        "mode": "std",
        "multi_shots": True,
        "multi_prompt": [
            {"prompt": "wide establishing shot", "duration": "3"},
            {"prompt": "product close-up", "duration": "4"},
        ],
    }
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare("kling-3.0", valid)
    assert seconds == 5
    payload = normalize_kie_video_input(spec.kie_model, clean)
    assert payload["duration"] == 5
    assert payload["multi_prompt"] == valid["multi_prompt"]

    too_long = {
        **valid,
        "multi_prompt": [
            {"prompt": "shot one", "duration": "8"},
            {"prompt": "shot two", "duration": "8"},
        ],
    }
    with pytest.raises(InvalidModelParametersError, match="must not exceed 15"):
        ModelCatalog.prepare("kling-3.0", too_long)
    with pytest.raises(KieVideoContractError, match="must not exceed 15"):
        normalize_kie_video_input("kling-3.0/video", too_long)


def test_kling_top_level_duration_is_still_bounded() -> None:
    base = {
        "prompt": "multi scene campaign",
        "mode": "std",
        "multi_shots": True,
        "multi_prompt": [{"prompt": "single shot", "duration": "3"}],
    }

    with pytest.raises(InvalidModelParametersError, match="between 3 and 15"):
        ModelCatalog.prepare("kling-3.0", {**base, "duration": 16})
    with pytest.raises(KieVideoContractError, match="between 3 and 15"):
        normalize_kie_video_input("kling-3.0/video", {**base, "duration": 16})

    with pytest.raises(KieVideoContractError, match="integer"):
        normalize_kie_video_input("kling-3.0/video", {**base, "duration": "invalid"})


def test_veo_public_schema_uses_current_quality_fast_lite_surface() -> None:
    schema = build_public_model_ui_schema(ModelCatalog.get("veo-3.1").public_dict())
    fields = {field["name"]: field for field in schema["fields"]}
    assert fields["veo_model"]["suggestions"] == ["veo3", "veo3_fast", "veo3_lite"]
    assert fields["generation_type"]["suggestions"] == [
        "TEXT_2_VIDEO",
        "FIRST_AND_LAST_FRAMES_2_VIDEO",
        "REFERENCE_2_VIDEO",
    ]


def test_veo_generation_modes_are_strict_before_billing_and_provider() -> None:
    valid_reference = {
        "prompt": "keep the product appearance",
        "image_urls": ["https://cdn.example/ref.png"],
        "veo_model": "veo3_fast",
        "aspect_ratio": "9:16",
        "generation_type": "REFERENCE_2_VIDEO",
        "enable_fallback": False,
        "enable_translation": True,
        "duration": 8,
    }
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare(
        "veo-3.1", valid_reference, billing_seconds=8
    )
    assert seconds == 8
    payload = normalize_kie_veo_input(clean)
    assert payload["veo_model"] == "veo3_fast"
    assert payload["generation_type"] == "REFERENCE_2_VIDEO"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["duration"] == 8

    text_with_image = {**valid_reference, "generation_type": "TEXT_2_VIDEO"}
    with pytest.raises(InvalidModelParametersError, match="cannot include image references"):
        ModelCatalog.prepare("veo-3.1", text_with_image, billing_seconds=8)
    with pytest.raises(KieVideoContractError, match="cannot include image references"):
        normalize_kie_veo_input(text_with_image)

    quality_reference = {**valid_reference, "veo_model": "veo3"}
    with pytest.raises(InvalidModelParametersError, match="Fast or Lite"):
        ModelCatalog.prepare("veo-3.1", quality_reference, billing_seconds=8)

    auto_reference = {**valid_reference, "aspect_ratio": "auto"}
    with pytest.raises(InvalidModelParametersError, match="16:9 or 9:16"):
        ModelCatalog.prepare("veo-3.1", auto_reference, billing_seconds=8)

    stale_alias = {**valid_reference, "veo_model": "veo3_fast_r2v"}
    with pytest.raises(InvalidModelParametersError, match="veo3_lite"):
        ModelCatalog.prepare("veo-3.1", stale_alias, billing_seconds=8)
