from __future__ import annotations

import pytest

from app.services.generations import GenerationService
from app.services.kie_image_contracts import KieImageContractError, normalize_kie_image_input
from app.services.kie_video_contracts import KieVideoContractError, normalize_kie_video_input
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema


def test_gemini_omni_exposes_all_current_output_controls() -> None:
    spec = ModelCatalog.get("gemini-omni-video")
    for field in ("aspect_ratio", "resolution", "seed"):
        assert field in spec.known_fields
    assert spec.min_seconds == 4
    assert spec.max_seconds == 10

    schema = build_public_model_ui_schema(spec.public_dict())
    fields = {item["name"]: item for item in schema["fields"]}
    assert fields["duration"]["suggestions"] == ["4", "6", "8", "10"]
    assert fields["aspect_ratio"]["suggestions"] == ["16:9", "9:16"]
    assert fields["resolution"]["suggestions"] == ["720p", "1080p", "4k"]
    assert fields["image_urls"]["max_items"] == 7
    assert fields["image_urls"]["max_size_mb"] == 10
    assert fields["audio_ids"]["max_items"] == 1
    assert fields["video_list"]["max_items"] == 1
    assert fields["character_ids"]["max_items"] == 3
    assert fields["seed"]["min"] == 0
    assert fields["seed"]["max"] == 2147483647


def test_gemini_omni_current_payload_is_exact() -> None:
    params = {
        "prompt": "turn this campaign asset into a cinematic clip",
        "image_urls": ["https://cdn.example/product.png"],
        "duration": 8,
        "aspect_ratio": "9:16",
        "resolution": "1080p",
        "seed": 42,
        "audio_ids": ["audio_demo"],
        "video_list": [],
        "character_ids": ["character_demo"],
    }
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare("gemini-omni-video", params)
    assert seconds == 8
    payload = normalize_kie_video_input(spec.kie_model, clean)
    assert payload["duration"] == "8"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["resolution"] == "1080p"
    assert payload["seed"] == 42
    assert payload["audio_ids"] == ["audio_demo"]


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"duration": 5}, "4, 6, 8 or 10"),
        ({"aspect_ratio": "1:1"}, "16:9 or 9:16"),
        ({"resolution": "2K"}, "720p, 1080p or 4k"),
        ({"seed": 2147483648}, "2147483647"),
        ({"audio_ids": ["a", "b"]}, "one audio ID"),
    ],
)
def test_gemini_omni_rejects_non_provider_values_before_billing(
    patch: dict[str, object], message: str
) -> None:
    params: dict[str, object] = {
        "prompt": "video",
        "duration": 4,
        "aspect_ratio": "16:9",
        "resolution": "720p",
    }
    params.update(patch)
    with pytest.raises(InvalidModelParametersError, match=message):
        ModelCatalog.prepare("gemini-omni-video", params)


def test_gemini_omni_provider_boundary_rejects_extra_audio_ids() -> None:
    with pytest.raises(KieVideoContractError, match="one audio ID"):
        normalize_kie_video_input(
            "gemini-omni-video",
            {
                "prompt": "video",
                "duration": 4,
                "aspect_ratio": "16:9",
                "resolution": "720p",
                "audio_ids": ["a", "b"],
            },
        )


def test_wan_image_prompt_and_upload_limits_are_public_and_enforced() -> None:
    schema = build_public_model_ui_schema(ModelCatalog.get("wan-2.7-image-pro").public_dict())
    fields = {item["name"]: item for item in schema["fields"]}
    assert fields["prompt"]["max_length"] == 5000
    assert fields["input_urls"]["max_items"] == 9
    assert fields["input_urls"]["max_size_mb"] == 10

    with pytest.raises(InvalidModelParametersError, match="5000"):
        ModelCatalog.prepare("wan-2.7-image-pro", {"prompt": "x" * 5001})
    with pytest.raises(KieImageContractError, match="5000"):
        normalize_kie_image_input("wan/2-7-image-pro", {"prompt": "x" * 5001})


def test_nano_banana_2_lite_exposes_current_reference_upload_limits() -> None:
    schema = build_public_model_ui_schema(ModelCatalog.get("nano-banana-2-lite").public_dict())
    field = next(item for item in schema["fields"] if item["name"] == "image_urls")
    assert field["max_items"] == 10
    assert field["max_size_mb"] == 30


@pytest.mark.asyncio
async def test_generation_pipeline_no_longer_bypasses_seedance_hybrid_rejection() -> None:
    with pytest.raises(InvalidModelParametersError, match="mutually exclusive"):
        await GenerationService.prepare_request(
            object(),  # no DB access is required for this model before validation
            model_id="seedance-2.0",
            prompt="keep the subject consistent",
            parameters={
                "first_frame_url": "https://cdn.example/first.png",
                "reference_image_urls": ["https://cdn.example/ref.png"],
                "duration": 5,
                "resolution": "720p",
                "aspect_ratio": "16:9",
            },
        )
