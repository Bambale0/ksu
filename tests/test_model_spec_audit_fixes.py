from __future__ import annotations

import pytest

from app.services.kie_video_contracts import (
    KieVideoContractError,
    normalize_kie_veo_input,
    normalize_kie_video_input,
)
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


SEEDANCE20 = (
    ("seedance-2.0", "bytedance/seedance-2"),
    ("seedance-2.0-fast", "bytedance/seedance-2-fast"),
    ("seedance-2.0-mini", "bytedance/seedance-2-mini"),
)


def test_seedance20_return_last_frame_is_public_and_preserved_for_provider() -> None:
    for model_id, provider in SEEDANCE20:
        spec = ModelCatalog.get(model_id)
        assert "return_last_frame" in spec.known_fields

        schema = build_public_model_ui_schema(spec.public_dict())
        fields = {item["name"]: item for item in schema["fields"]}
        assert fields["return_last_frame"]["control"] == "toggle"
        assert schema["defaults"]["return_last_frame"] is False

        payload = normalize_kie_video_input(
            provider,
            {
                "prompt": "camera follows the subject",
                "duration": 5,
                "resolution": "720p",
                "aspect_ratio": "16:9",
                "return_last_frame": True,
            },
        )
        assert payload["return_last_frame"] is True


def test_veo_31_resolution_and_duration_are_public_billed_and_provider_validated() -> None:
    spec = ModelCatalog.get("veo-3.1")
    assert "resolution" in spec.known_fields
    assert "duration" in spec.known_fields

    schema = build_public_model_ui_schema(spec.public_dict())
    fields = {item["name"]: item for item in schema["fields"]}
    assert fields["resolution"]["suggestions"] == ["720p", "1080p", "4k"]
    assert fields["duration"]["suggestions"] == [4, 6, 8]

    params = {
        "prompt": "cinematic tracking shot",
        "veo_model": "veo3_fast",
        "aspect_ratio": "auto",
        "generation_type": "TEXT_2_VIDEO",
        "resolution": "1080p",
        "duration": 6,
    }
    _spec, clean, _cost, seconds, _unit = ModelCatalog.prepare("veo-3.1", params)
    assert seconds == 6
    assert clean["resolution"] == "1080p"

    payload = normalize_kie_veo_input(clean)
    assert payload["resolution"] == "1080p"
    assert payload["duration"] == 6

    with pytest.raises(InvalidModelParametersError, match="4, 6 or 8"):
        ModelCatalog.prepare("veo-3.1", {**params, "duration": 5})
    with pytest.raises(KieVideoContractError, match="4, 6 or 8"):
        normalize_kie_veo_input({**params, "duration": 5})

    with pytest.raises(InvalidModelParametersError, match="720p, 1080p or 4k"):
        ModelCatalog.prepare("veo-3.1", {**params, "resolution": "1440p"})
    with pytest.raises(KieVideoContractError, match="720p, 1080p or 4k"):
        normalize_kie_veo_input({**params, "resolution": "1440p"})


def test_seedance20_frame_and_multimodal_modes_are_mutually_exclusive_everywhere() -> None:
    invalid = {
        "prompt": "keep the subject consistent",
        "first_frame_url": "https://cdn.example/first.png",
        "reference_image_urls": ["https://cdn.example/ref.png"],
        "duration": 5,
        "resolution": "720p",
        "aspect_ratio": "16:9",
    }

    with pytest.raises(InvalidModelParametersError, match="mutually exclusive"):
        ModelCatalog.prepare("seedance-2.0", invalid)

    with pytest.raises(KieVideoContractError, match="mutually exclusive"):
        normalize_kie_video_input("bytedance/seedance-2", invalid)


def test_grok_i2v_task_reference_preserves_exact_current_contract() -> None:
    params = {
        "task_id": "task_grok_123",
        "index": 2,
        "prompt": "bring the selected frame to life",
        "mode": "spicy",
        "duration": 6,
        "resolution": "1080p",
        "aspect_ratio": "16:9",
        "nsfw_checker": True,
    }
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare("grok-video-i2v", params)
    assert spec.kie_model == "grok-imagine/image-to-video"
    assert seconds == 6

    payload = normalize_kie_video_input(spec.kie_model, clean)
    assert payload["task_id"] == "task_grok_123"
    assert payload["index"] == 2
    assert payload["mode"] == "spicy"
    assert payload["resolution"] == "1080p"
    assert payload["aspect_ratio"] == "16:9"
    assert payload["nsfw_checker"] is True
    assert not payload.get("image_urls")


def test_grok_i2v_external_image_spicy_mode_is_rejected_before_billing_and_provider() -> None:
    params = {
        "image_urls": ["https://cdn.example/source.png"],
        "prompt": "animate",
        "mode": "spicy",
        "duration": 6,
        "resolution": "720p",
        "aspect_ratio": "16:9",
    }

    with pytest.raises(InvalidModelParametersError, match="Spicy"):
        ModelCatalog.prepare("grok-video-i2v", params)

    with pytest.raises(KieVideoContractError, match="Spicy"):
        normalize_kie_video_input("grok-imagine/image-to-video", params)


def test_grok_upscale_resolution_is_limited_to_provider_enum() -> None:
    valid = {"task_id": "task_video_123", "resolution": "720p"}
    spec, clean, _cost, _seconds, _unit = ModelCatalog.prepare(
        "grok-video-upscale", valid, billing_seconds=6
    )
    payload = normalize_kie_video_input(spec.kie_model, clean)
    assert payload["resolution"] == "720p"

    with pytest.raises(InvalidModelParametersError, match="720p or 1080p"):
        ModelCatalog.prepare(
            "grok-video-upscale",
            {"task_id": "task_video_123", "resolution": "4K"},
            billing_seconds=6,
        )
    with pytest.raises(KieVideoContractError, match="720p or 1080p"):
        normalize_kie_video_input(
            "grok-imagine/upscale", {"task_id": "task_video_123", "resolution": "4K"}
        )


def test_grok_extend_allows_documented_empty_or_omitted_prompt_and_keeps_string_duration_enum() -> None:
    params = {
        "task_id": "task_grok_12345678",
        "prompt": "",
        "extend_at": 2,
        "extend_times": "6",
    }
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare("grok-video-extend", params)
    assert seconds == 6

    payload = normalize_kie_video_input(spec.kie_model, clean)
    assert payload == params
    assert isinstance(payload["extend_at"], int)
    assert isinstance(payload["extend_times"], str)

    missing_prompt = {"task_id": "task_grok_123", "extend_at": 2, "extend_times": "6"}
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare(
        "grok-video-extend", missing_prompt
    )
    assert seconds == 6
    assert clean["prompt"] == ""

    payload = normalize_kie_video_input(spec.kie_model, missing_prompt)
    assert payload["prompt"] == ""
    assert payload["extend_at"] == 2
    assert payload["extend_times"] == "6"

    with pytest.raises(InvalidModelParametersError, match="prompt must be a string"):
        ModelCatalog.prepare(
            "grok-video-extend",
            {
                "task_id": "task_grok_123",
                "prompt": None,
                "extend_at": 2,
                "extend_times": "6",
            },
        )

    with pytest.raises(KieVideoContractError, match="prompt must be a string"):
        normalize_kie_video_input(
            "grok-imagine/extend",
            {
                "task_id": "task_grok_123",
                "prompt": None,
                "extend_at": 2,
                "extend_times": "6",
            },
        )

    with pytest.raises(InvalidModelParametersError, match="at least 2"):
        ModelCatalog.prepare(
            "grok-video-extend",
            {"task_id": "task_grok_123", "prompt": "", "extend_at": 1, "extend_times": "6"},
        )
