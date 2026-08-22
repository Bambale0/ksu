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
    assert ModelCatalog.get(AVATAR_PRO_ID).known_fields == (
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
            "aspect_ratio": "16:9",
            "negative_prompt": "blur",
            "cfg_scale": 0.5,
            "nsfw_checker": True,
        },
    )
    assert spec.kie_model == T2V_PROVIDER
    assert clean["duration"] == "5"
    assert clean["aspect_ratio"] == "16:9"
    assert seconds == 5

    for bad_duration in ("3", "6", "15"):
        with pytest.raises(InvalidModelParametersError):
            ModelCatalog.prepare(
                T2V_ID,
                {"prompt": "x", "duration": bad_duration, "aspect_ratio": "16:9"},
            )
    with pytest.raises(InvalidModelParametersError):
        ModelCatalog.prepare(
            T2V_ID,
            {"prompt": "x", "duration": "5", "aspect_ratio": "4:3"},
        )


def test_kling_25_i2v_requires_image_and_supports_optional_tail_frame() -> None:
    spec, clean, _cost, seconds, _unit = ModelCatalog.prepare(
        I2V_ID,
        {
            "prompt": "camera slowly moves",
            "image_url": "https://example.com/start.jpg",
            "tail_image_url": "https://example.com/end.jpg",
            "duration": "10",
            "negative_prompt": "flicker",
            "cfg_scale": 0.5,
            "nsfw_checker": True,
        },
    )
    assert spec.kie_model == I2V_PROVIDER
    assert clean["image_url"].endswith("start.jpg")
    assert clean["tail_image_url"].endswith("end.jpg")
    assert seconds == 10

    with pytest.raises(InvalidModelParametersError):
        ModelCatalog.prepare(
            I2V_ID,
            {"prompt": "x", "duration": "5"},
        )


def test_kling_avatar_contracts_use_audio_duration_for_billing() -> None:
    std = ModelCatalog.get(AVATAR_STD_ID)
    pro = ModelCatalog.get(AVATAR_PRO_ID)
    assert std.duration_field is None
    assert pro.duration_field is None
    assert std.min_seconds == 1 and std.max_seconds == 300
    assert pro.min_seconds == 1 and pro.max_seconds == 300

    for model_id in (AVATAR_STD_ID, AVATAR_PRO_ID):
        spec, clean, _cost, seconds, _unit = ModelCatalog.prepare(
            model_id,
            {
                "image_url": "https://example.com/avatar.jpg",
                "audio_url": "https://example.com/voice.mp3",
                "prompt": "natural expression",
            },
            billing_seconds=12,
        )
        assert spec.id == model_id
        assert clean["image_url"].endswith("avatar.jpg")
        assert clean["audio_url"].endswith("voice.mp3")
        assert seconds == 12


def test_kie_kling_25_t2v_payload_is_provider_exact() -> None:
    result = normalize_kie_video_input(
        T2V_PROVIDER,
        {
            "prompt": "cinematic city",
            "duration": "5",
            "aspect_ratio": "16:9",
            "negative_prompt": "blur",
            "cfg_scale": 0.5,
            "nsfw_checker": True,
        },
    )
    assert result == {
        "prompt": "cinematic city",
        "duration": "5",
        "aspect_ratio": "16:9",
        "negative_prompt": "blur",
        "cfg_scale": 0.5,
        "nsfw_checker": True,
    }
    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            T2V_PROVIDER,
            {"prompt": "x", "duration": "7", "aspect_ratio": "16:9"},
        )


def test_kie_kling_25_i2v_payload_is_provider_exact() -> None:
    result = normalize_kie_video_input(
        I2V_PROVIDER,
        {
            "prompt": "camera move",
            "image_url": "https://example.com/start.jpg",
            "tail_image_url": "https://example.com/end.jpg",
            "duration": "10",
            "negative_prompt": "flicker",
            "cfg_scale": 0.5,
            "nsfw_checker": True,
        },
    )
    assert result == {
        "prompt": "camera move",
        "image_url": "https://example.com/start.jpg",
        "tail_image_url": "https://example.com/end.jpg",
        "duration": "10",
        "negative_prompt": "flicker",
        "cfg_scale": 0.5,
        "nsfw_checker": True,
    }


def test_kie_kling_avatar_payloads_are_provider_exact() -> None:
    std = normalize_kie_video_input(
        AVATAR_STD_PROVIDER,
        {
            "image_url": "https://example.com/avatar.jpg",
            "audio_url": "https://example.com/voice.mp3",
            "prompt": "natural expression",
        },
    )
    assert std == {
        "image_url": "https://example.com/avatar.jpg",
        "audio_url": "https://example.com/voice.mp3",
        "prompt": "natural expression",
    }
    pro = normalize_kie_video_input(
        AVATAR_PRO_PROVIDER,
        {
            "image_url": "https://example.com/avatar.jpg",
            "audio_url": "https://example.com/voice.mp3",
            "prompt": "natural expression",
        },
    )
    assert pro == std


def test_generation_provider_maps_current_kling_provider_ids() -> None:
    for model_id, provider in (
        (T2V_ID, T2V_PROVIDER),
        (I2V_ID, I2V_PROVIDER),
        (AVATAR_STD_ID, AVATAR_STD_PROVIDER),
        (AVATAR_PRO_ID, AVATAR_PRO_PROVIDER),
    ):
        generation = Generation(
            kind="video",
            prompt="x",
            parameters={"_model_id": model_id, "_provider_model": provider},
        )
        assert GenerationProviderService._model_for(generation) == provider


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

    # Historical package/balance migration helper deliberately remains 10x;
    # runtime generation tariffs are already denominated in public 1-RUB ROX.
    assert InternalCreditService.legacy_credits_to_rox(Decimal("3")) == Decimal("30")
