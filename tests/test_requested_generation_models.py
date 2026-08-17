import pytest

from app.services.model_catalog import (
    InvalidModelParametersError,
    ModelCatalog,
    UnknownModelError,
)
from app.services.model_ui_contract import build_public_model_ui_schema


def test_requested_reference_models_are_kie_only() -> None:
    models = {item["id"]: item for item in ModelCatalog.list()}
    expected = {
        "nano-banana-pro",
        "wan-2.7-image",
        "gpt-image-2-t2i",
        "nano-banana-2",
        "nano-banana-2-lite",
        "seedream-4.5-t2i",
        "seedream-5-pro-t2i",
        "seedance-2.0",
        "seedance-2.5",
        "kling-3.0",
        "veo-3.1",
        "grok-video-t2v",
        "grok-video-1.5",
        "gemini-omni-video",
        "kling-motion-3.0",
        "kling-motion-2.6",
    }
    assert expected.issubset(models)
    assert "heygen-avatar" not in models
    assert "kling-3.0-omni" not in models
    assert models["kling-3.0"]["kie_model"] == "kling-3.0/video"
    assert models["gemini-omni-video"]["kie_model"] == "gemini-omni-video"
    assert models["veo-3.1"]["media_type"] == "video"


@pytest.mark.parametrize("model_id", ["heygen-avatar", "kling-3.0-omni"])
def test_non_kie_models_are_rejected(model_id: str) -> None:
    with pytest.raises(UnknownModelError):
        ModelCatalog.get(model_id)


def test_kling_3_full_spec_accepts_single_and_valid_multishot() -> None:
    spec, clean, _, seconds, _ = ModelCatalog.prepare(
        "kling-3.0",
        {
            "prompt": "Cinematic dog running",
            "image_urls": ["https://example.com/start.png"],
            "sound": True,
            "duration": 5,
            "aspect_ratio": "16:9",
            "mode": "pro",
            "multi_shots": False,
            "kling_elements": [
                {
                    "name": "dog",
                    "description": "hero dog",
                    "element_input_urls": [
                        "https://example.com/a.png",
                        "https://example.com/b.png",
                    ],
                }
            ],
        },
    )
    assert spec.kie_model == "kling-3.0/video"
    assert seconds == 5
    assert clean["mode"] == "pro"

    _, multi, _, seconds, _ = ModelCatalog.prepare(
        "kling-3.0",
        {
            "duration": 5,
            "multi_shots": True,
            "multi_prompt": [
                {"prompt": "shot one", "duration": 2},
                {"prompt": "shot two", "duration": 3},
            ],
        },
    )
    assert seconds == 5
    assert len(multi["multi_prompt"]) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"duration": 5, "image_urls": ["a", "b", "c"]},
        {
            "duration": 5,
            "multi_shots": True,
            "multi_prompt": [{"prompt": "one", "duration": 3}],
        },
        {
            "duration": 5,
            "kling_elements": [{"name": "x", "element_input_urls": ["a"]}],
        },
    ],
)
def test_kling_3_rejects_provider_invalid_shapes(payload: dict) -> None:
    with pytest.raises(InvalidModelParametersError):
        ModelCatalog.prepare("kling-3.0", payload)


def test_gemini_omni_enforces_provider_quota() -> None:
    valid = {
        "prompt": "film",
        "duration": 4,
        "image_urls": ["a", "b"],
        "video_list": [{"url": "v", "start": 0, "ends": 4}],
        "character_ids": ["c1", "c2", "c3"],
        "audio_ids": ["a1"],
    }
    ModelCatalog.prepare("gemini-omni-video", valid)

    invalid = {**valid, "image_urls": ["a", "b", "c"]}
    with pytest.raises(InvalidModelParametersError, match="quota"):
        ModelCatalog.prepare("gemini-omni-video", invalid)


def test_veo_modes_and_reference_rules_are_server_validated() -> None:
    ModelCatalog.prepare(
        "veo-3.1",
        {
            "prompt": "scene",
            "veo_model": "veo3_fast",
            "generation_type": "REFERENCE_2_VIDEO",
            "image_urls": ["https://example.com/reference.png"],
        },
        billing_seconds=8,
    )
    with pytest.raises(InvalidModelParametersError, match="exactly two"):
        ModelCatalog.prepare(
            "veo-3.1",
            {
                "prompt": "scene",
                "generation_type": "FIRST_AND_LAST_FRAMES_2_VIDEO",
                "image_urls": ["https://example.com/only-one.png"],
            },
            billing_seconds=8,
        )


def test_requested_kie_models_have_rich_dynamic_controls() -> None:
    models = {item["id"]: item for item in ModelCatalog.list()}

    kling = build_public_model_ui_schema(models["kling-3.0"])
    controls = {field["name"]: field for field in kling["fields"]}
    assert controls["multi_prompt"]["control"] == "json"
    assert controls["kling_elements"]["control"] == "json"
    assert controls["sound"]["control"] == "toggle"
    assert controls["image_urls"]["max_items"] == 2

    veo = build_public_model_ui_schema(models["veo-3.1"])
    controls = {field["name"]: field for field in veo["fields"]}
    assert controls["veo_model"]["control"] == "combobox"
    assert controls["generation_type"]["control"] == "combobox"
    assert veo["billing_seconds"]["required"] is True

    gemini = build_public_model_ui_schema(models["gemini-omni-video"])
    controls = {field["name"]: field for field in gemini["fields"]}
    assert controls["video_list"]["control"] == "json"
    assert controls["character_ids"]["control"] == "json"
