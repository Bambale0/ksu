from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.generations import GenerationService
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.seedance25_contract import normalize_seedance25_input


def test_seedance25_contract_accepts_current_kie_surface() -> None:
    payload = normalize_seedance25_input(
        {
            "prompt": "cinematic scene",
            "reference_image_urls": [f"https://example.com/image-{index}.png" for index in range(30)],
            "reference_video_urls": [f"https://example.com/video-{index}.mp4" for index in range(10)],
            "reference_audio_urls": [f"https://example.com/audio-{index}.mp3" for index in range(10)],
            "generate_audio": True,
            "return_last_frame": True,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
            "duration": 30,
            "output_format": "mov",
            "web_search": True,
            "nsfw_checker": False,
            "fixed_lens": True,
            "_model_id": "seedance-2.5",
        }
    )

    assert payload["resolution"] == "720p"
    assert payload["aspect_ratio"] == "adaptive"
    assert payload["duration"] == 30
    assert payload["output_format"] == "mov"
    assert len(payload["reference_image_urls"]) == 30
    assert len(payload["reference_video_urls"]) == 10
    assert len(payload["reference_audio_urls"]) == 10
    assert "fixed_lens" not in payload
    assert "_model_id" not in payload


def test_seedance25_contract_rejects_unknown_provider_fields() -> None:
    with pytest.raises(InvalidModelParametersError, match="Unsupported Seedance 2.5 field"):
        normalize_seedance25_input(
            {
                "prompt": "x",
                "duration": 4,
                "made_up_future_flag": True,
            }
        )


@pytest.mark.parametrize(
    ("field", "count"),
    [
        ("reference_image_urls", 31),
        ("reference_video_urls", 11),
        ("reference_audio_urls", 11),
    ],
)
def test_seedance25_contract_enforces_reference_limits(field: str, count: int) -> None:
    with pytest.raises(InvalidModelParametersError, match="at most"):
        normalize_seedance25_input(
            {
                "prompt": "x",
                "duration": 4,
                field: [f"https://example.com/{index}" for index in range(count)],
            }
        )


@pytest.mark.parametrize("duration", [-1, 1, 3, 31])
def test_seedance25_auto_or_out_of_range_duration_is_rejected_until_settlement_exists(
    duration: int,
) -> None:
    with pytest.raises(InvalidModelParametersError, match="4-30"):
        normalize_seedance25_input({"prompt": "x", "duration": duration})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resolution", "1080p"),
        ("resolution", "4K"),
        ("aspect_ratio", "2:3"),
        ("output_format", "webm"),
    ],
)
def test_seedance25_contract_rejects_unsupported_current_provider_enums(
    field: str,
    value: str,
) -> None:
    with pytest.raises(InvalidModelParametersError, match="Unsupported"):
        normalize_seedance25_input({"prompt": "x", "duration": 4, field: value})


def test_seedance25_frame_and_multireference_modes_are_mutually_exclusive() -> None:
    with pytest.raises(InvalidModelParametersError, match="mutually exclusive"):
        normalize_seedance25_input(
            {
                "prompt": "x",
                "duration": 4,
                "first_frame_url": "https://example.com/first.png",
                "reference_image_urls": ["https://example.com/ref.png"],
            }
        )


def test_seedance25_catalog_and_public_ui_match_current_provider_contract() -> None:
    model = next(item for item in ModelCatalog.list() if item["id"] == "seedance-2.5")
    known_fields = set(model["known_fields"])

    assert model["min_seconds"] == 4
    assert model["max_seconds"] == 30
    assert "fixed_lens" not in known_fields
    assert {"output_format", "nsfw_checker"}.issubset(known_fields)

    spec = ModelCatalog.get("seedance-2.5")
    assert spec.min_seconds == 4
    assert spec.max_seconds == 30
    assert "fixed_lens" not in spec.known_fields
    assert {"output_format", "nsfw_checker"}.issubset(spec.known_fields)

    schema = build_public_model_ui_schema(model)
    fields = {field["name"]: field for field in schema["fields"]}

    assert "fixed_lens" not in fields
    assert fields["duration"]["min"] == 4
    assert fields["duration"]["max"] == 30
    assert fields["resolution"]["suggestions"] == ["480p", "720p"]
    assert fields["aspect_ratio"]["suggestions"] == [
        "16:9",
        "4:3",
        "1:1",
        "3:4",
        "9:16",
        "21:9",
        "adaptive",
    ]
    assert fields["output_format"]["suggestions"] == ["mp4", "mov"]
    assert fields["nsfw_checker"]["control"] == "toggle"
    assert fields["reference_image_urls"]["max_items"] == 30
    assert fields["reference_video_urls"]["max_items"] == 10
    assert fields["reference_audio_urls"]["max_items"] == 10
    assert schema["defaults"]["output_format"] == "mp4"


@pytest.mark.asyncio
async def test_seedance25_generation_prevalidation_runs_before_billing() -> None:
    _spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
        object(),
        model_id="seedance-2.5",
        prompt="cinematic city",
        parameters={
            "duration": 4,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "output_format": "mp4",
            "nsfw_checker": True,
        },
    )

    assert seconds == 4
    assert clean["output_format"] == "mp4"
    assert clean["nsfw_checker"] is True
    assert cost == unit_price * Decimal("4")

    with pytest.raises(InvalidModelParametersError, match="4-30"):
        await GenerationService.prepare_request(
            object(),
            model_id="seedance-2.5",
            prompt="too short",
            parameters={"duration": 3},
        )

    with pytest.raises(InvalidModelParametersError, match="Unsupported Seedance 2.5 field"):
        await GenerationService.prepare_request(
            object(),
            model_id="seedance-2.5",
            prompt="invalid provider field",
            parameters={"duration": 4, "unexpected_provider_field": "x"},
        )
