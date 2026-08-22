from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import Generation
from app.services.credits import InternalCreditService
from app.services.generation_provider import GenerationProviderService
from app.services.generations import GenerationService
from app.services.kie_video_contracts import KieVideoContractError, normalize_kie_video_input
from app.services.model_catalog import (
    InvalidModelParametersError,
    ModelCatalog,
)
from app.services.model_ui import build_model_ui_schema


T2V_ID = "kling-2.5-turbo-pro-t2v"
I2V_ID = "kling-2.5-turbo-pro-i2v"
AVATAR_STD_ID = "kling-avatar-standard"
AVATAR_PRO_ID = "kling-avatar-pro"

T2V_PROVIDER = "kling/v2-5-turbo-text-to-video-pro"
I2V_PROVIDER = "kling/v2-5-turbo-image-to-video-pro"
AVATAR_STD_PROVIDER = "kling/ai-avatar-standard"
AVATAR_PRO_PROVIDER = "kling/ai-avatar-pro"


def _public_model(model_id: str) -> dict[str, object]:
    return next(item for item in ModelCatalog.list() if item["id"] == model_id)


def test_current_kling_models_are_registered_with_exact_provider_ids() -> None:
    assert ModelCatalog.get(T2V_ID).kie_model == T2V_PROVIDER
    assert ModelCatalog.get(I2V_ID).kie_model == I2V_PROVIDER
    assert ModelCatalog.get(AVATAR_STD_ID).kie_model == AVATAR_STD_PROVIDER
    assert ModelCatalog.get(AVATAR_PRO_ID).kie_model == AVATAR_PRO_PROVIDER

    assert ModelCatalog.get(T2V_ID).known_fields == (
        "prompt",
        "duration",
        "aspect_ratio",
        "negative_prompt",
        "cfg_scale",
        "nsfw_checker",
    )
    assert ModelCatalog.get(I2V_ID).known_fields == (
        "prompt",
        "image_url",
        "tail_image_url",
        "duration",
        "negative_prompt",
        "cfg_scale",
        "nsfw_checker",
    )
    assert ModelCatalog.get(AVATAR_STD_ID).known_fields == (
        "image_url",
        "audio_url",
        "prompt",
    )


def test_kling_25_t2v_accepts_only_current_callable_duration_and_aspect() -> None:
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare(
        T2V_ID,
        {
            "prompt": "cinematic city",
            "duration": "5",
            "aspect_ratio": "9:16",
            "negative_prompt": "blur",
            "cfg_scale": "0.5",
            "nsfw_checker": True,
        },
    )
    assert spec.kie_model == T2V_PROVIDER
    assert seconds == 5
    assert clean["duration"] == 5
    assert clean["aspect_ratio"] == "9:16"
    assert clean["cfg_scale"] == 0.5

    with pytest.raises(InvalidModelParametersError, match="5 or 10"):
        ModelCatalog.prepare(T2V_ID, {"prompt": "x", "duration": 6})

    with pytest.raises(InvalidModelParametersError, match="aspect_ratio"):
        ModelCatalog.prepare(
            T2V_ID,
            {"prompt": "x", "duration": 5, "aspect_ratio": "4:3"},
        )


def test_kling_25_rejects_unknown_public_fields_before_provider_submission() -> None:
    with pytest.raises(InvalidModelParametersError, match="Unsupported"):
        ModelCatalog.prepare(
            T2V_ID,
            {"prompt": "x", "duration": 5, "legacy_mode": "pro"},
        )

    with pytest.raises(InvalidModelParametersError, match="Unsupported"):
        ModelCatalog.prepare(
            I2V_ID,
            {
                "prompt": "x",
                "duration": 5,
                "image_url": "https://cdn.example/start.png",
                "aspect_ratio": "16:9",
            },
        )


def test_kling_25_i2v_requires_https_first_frame_and_allows_optional_tail() -> None:
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare(
        I2V_ID,
        {
            "prompt": "camera pushes in",
            "duration": 10,
            "image_url": "https://cdn.example/start.png",
            "tail_image_url": "https://cdn.example/end.png?sig=1",
            "cfg_scale": 0.5,
            "nsfw_checker": False,
        },
    )
    assert spec.kie_model == I2V_PROVIDER
    assert seconds == 10
    assert clean["tail_image_url"].startswith("https://")

    with pytest.raises(InvalidModelParametersError, match="Missing required field: image_url"):
        ModelCatalog.prepare(I2V_ID, {"prompt": "x", "duration": 5})

    with pytest.raises(InvalidModelParametersError, match="HTTPS URL"):
        ModelCatalog.prepare(
            I2V_ID,
            {
                "prompt": "x",
                "duration": 5,
                "image_url": "http://cdn.example/start.png",
            },
        )


def test_avatar_uses_audio_duration_for_billing_without_provider_duration_field() -> None:
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare(
        AVATAR_STD_ID,
        {
            "image_url": "https://cdn.example/avatar.png",
            "audio_url": "https://cdn.example/speech.mp3",
            "prompt": "friendly, subtle head movement",
        },
        billing_seconds=300,
    )
    assert spec.duration_field is None
    assert spec.min_seconds == 1
    assert spec.max_seconds == 300
    assert seconds == 300
    assert "duration" not in clean
    assert "billing_seconds" not in clean

    with pytest.raises(InvalidModelParametersError, match="Maximum duration is 300s"):
        ModelCatalog.prepare(
            AVATAR_STD_ID,
            {
                "image_url": "https://cdn.example/avatar.png",
                "audio_url": "https://cdn.example/speech.mp3",
            },
            billing_seconds=301,
        )


def test_avatar_prompt_field_is_always_sent_but_empty_guidance_is_allowed() -> None:
    _spec, clean, _cost, seconds, _unit = ModelCatalog.prepare(
        AVATAR_PRO_ID,
        {
            "image_url": "https://cdn.example/avatar.png",
            "audio_url": "https://cdn.example/song.ogg",
        },
        billing_seconds=45,
    )
    assert seconds == 45
    assert clean["prompt"] == ""

    normalized = normalize_kie_video_input(AVATAR_PRO_PROVIDER, clean)
    assert normalized == {
        "image_url": "https://cdn.example/avatar.png",
        "audio_url": "https://cdn.example/song.ogg",
        "prompt": "",
    }


def test_provider_normalizer_emits_only_current_kling_25_contract() -> None:
    t2v = normalize_kie_video_input(
        T2V_PROVIDER,
        {
            "prompt": "runner in the rain",
            "duration": 5,
            "aspect_ratio": "16:9",
            "negative_prompt": "blur",
            "cfg_scale": 0.5,
            "nsfw_checker": True,
        },
    )
    assert t2v == {
        "prompt": "runner in the rain",
        "duration": "5",
        "aspect_ratio": "16:9",
        "negative_prompt": "blur",
        "cfg_scale": 0.5,
        "nsfw_checker": True,
    }

    i2v = normalize_kie_video_input(
        I2V_PROVIDER,
        {
            "prompt": "turn toward camera",
            "image_url": "https://cdn.example/start.png",
            "tail_image_url": "https://cdn.example/end.png",
            "duration": 10,
            "cfg_scale": 0.5,
        },
    )
    assert i2v["duration"] == "10"
    assert i2v["tail_image_url"] == "https://cdn.example/end.png"
    assert "aspect_ratio" not in i2v

    with pytest.raises(KieVideoContractError, match="Unsupported fields"):
        normalize_kie_video_input(
            I2V_PROVIDER,
            {
                "prompt": "x",
                "image_url": "https://cdn.example/start.png",
                "duration": 5,
                "legacy_field": True,
            },
        )


def test_avatar_billing_metadata_never_reaches_kie_input() -> None:
    generation = Generation(
        prompt="",
        input_url=None,
        parameters={
            "image_url": "https://cdn.example/avatar.png",
            "audio_url": "https://cdn.example/audio.wav",
            "prompt": "",
            "_model_id": AVATAR_STD_ID,
            "_kie_model": AVATAR_STD_PROVIDER,
            "_billing_mode": "per_second",
            "_billing_seconds": 42,
            "_unit_price_rox": "20",
        },
    )
    provider_input = GenerationProviderService._input_for(generation)
    assert provider_input == {
        "image_url": "https://cdn.example/avatar.png",
        "audio_url": "https://cdn.example/audio.wav",
        "prompt": "",
    }
    assert "duration" not in provider_input
    assert "billing_seconds" not in provider_input


def test_current_kling_ui_schema_matches_upload_and_duration_contracts() -> None:
    t2v_schema = build_model_ui_schema(_public_model(T2V_ID))
    t2v_fields = {item["name"]: item for item in t2v_schema["fields"]}
    assert t2v_fields["duration"]["control"] == "combobox"
    assert t2v_fields["duration"]["suggestions"] == ["5", "10"]
    assert t2v_fields["aspect_ratio"]["suggestions"] == ["16:9", "9:16", "1:1"]
    assert t2v_schema["defaults"]["nsfw_checker"] is True

    i2v_schema = build_model_ui_schema(_public_model(I2V_ID))
    i2v_fields = {item["name"]: item for item in i2v_schema["fields"]}
    assert i2v_fields["image_url"]["max_size_mb"] == 10
    assert i2v_fields["tail_image_url"]["max_size_mb"] == 10

    avatar_schema = build_model_ui_schema(_public_model(AVATAR_PRO_ID))
    avatar_fields = {item["name"]: item for item in avatar_schema["fields"]}
    assert avatar_fields["image_url"]["max_size_mb"] == 10
    assert avatar_fields["audio_url"]["max_size_mb"] == 100
    assert avatar_schema["billing_seconds"] == {
        "label": "Длительность аудио",
        "min": 1,
        "max": 300,
        "required": True,
    }


def test_roxy_default_public_rates_for_current_kling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "generation_pricing_json", "{}")
    assert GenerationService._effective_unit_price(model_id=T2V_ID, parameters={}) == Decimal("3")
    assert GenerationService._effective_unit_price(model_id=I2V_ID, parameters={}) == Decimal("3")
    assert GenerationService._effective_unit_price(model_id=AVATAR_STD_ID, parameters={}) == Decimal("2")
    assert GenerationService._effective_unit_price(model_id=AVATAR_PRO_ID, parameters={}) == Decimal("3")

    # Historical migration compatibility remains 10x, but live generation prices are 1:1 ROX.
    assert InternalCreditService.legacy_credits_to_rox(Decimal("3")) == Decimal("30")
