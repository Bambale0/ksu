from __future__ import annotations

import pytest

from app.services.kie_video_contracts import (
    KieVideoContractError,
    normalize_kie_veo_input,
    normalize_kie_video_input,
)
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


def test_kling_frame_flow_has_no_forced_aspect_ratio_default() -> None:
    schema = build_public_model_ui_schema(ModelCatalog.get("kling-3.0").public_dict())
    assert "aspect_ratio" not in schema["defaults"]

    params = {
        "prompt": "camera moves around the subject",
        "image_urls": ["https://cdn.example/first.png"],
        "sound": True,
        "duration": 5,
        "mode": "pro",
        "multi_shots": False,
    }
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare("kling-3.0", params)
    assert seconds == 5
    payload = normalize_kie_video_input(spec.kie_model, clean)
    assert "aspect_ratio" not in payload

    invalid = {**params, "aspect_ratio": "16:9"}
    with pytest.raises(InvalidModelParametersError, match="aspect_ratio must be omitted"):
        ModelCatalog.prepare("kling-3.0", invalid)
    with pytest.raises(KieVideoContractError, match="aspect_ratio must be omitted"):
        normalize_kie_video_input("kling-3.0/video", invalid)


def test_kling_multishot_uses_storyboard_cap_not_stale_duration_equality() -> None:
    params = {
        "multi_shots": True,
        "duration": 5,
        "mode": "pro",
        "sound": True,
        "multi_prompt": [
            {"prompt": "first shot", "duration": 3},
            {"prompt": "second shot", "duration": 3},
        ],
    }
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare("kling-3.0", params)
    assert seconds == 5
    payload = normalize_kie_video_input(spec.kie_model, clean)
    assert payload["duration"] == 5
    assert sum(item["duration"] for item in payload["multi_prompt"]) == 6

    too_many = {
        "multi_shots": True,
        "duration": 15,
        "mode": "pro",
        "multi_prompt": [{"prompt": f"shot {index}", "duration": 1} for index in range(6)],
    }
    with pytest.raises(InvalidModelParametersError, match="one to five"):
        ModelCatalog.prepare("kling-3.0", too_many)

    too_long = {
        "multi_shots": True,
        "duration": 15,
        "mode": "pro",
        "multi_prompt": [
            {"prompt": "one", "duration": 8},
            {"prompt": "two", "duration": 8},
        ],
    }
    with pytest.raises(InvalidModelParametersError, match="must not exceed 15"):
        ModelCatalog.prepare("kling-3.0", too_long)


def test_kling_multishot_top_duration_stays_strict_when_equality_check_is_bypassed() -> None:
    base = {
        "multi_shots": True,
        "mode": "pro",
        "multi_prompt": [
            {"prompt": "one", "duration": 3},
            {"prompt": "two", "duration": 3},
        ],
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
