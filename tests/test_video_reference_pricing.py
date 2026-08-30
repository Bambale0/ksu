from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import settings
from app.services.generations import GenerationService


def _seedance_params() -> dict[str, object]:
    return {
        "duration": 5,
        "resolution": "720p",
        "aspect_ratio": "adaptive",
        "output_format": "mp4",
        "generate_audio": False,
        "return_last_frame": False,
        "web_search": False,
        "nsfw_checker": True,
    }


@pytest.mark.asyncio
async def test_video_reference_doubles_authoritative_generation_price() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = '{"seedance-2.5":{"per_second":10}}'
    try:
        spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
            object(),  # type: ignore[arg-type]
            model_id="seedance-2.5",
            prompt="follow this motion reference",
            parameters={
                **_seedance_params(),
                "reference_video_urls": ["https://cdn.example/motion.mp4"],
            },
        )
    finally:
        settings.generation_pricing_json = previous

    assert spec.id == "seedance-2.5"
    assert clean["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert seconds == 5
    assert unit_price == Decimal("20")
    assert cost == Decimal("100.00")


@pytest.mark.asyncio
async def test_image_reference_keeps_normal_generation_price() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = '{"seedance-2.5":{"per_second":10}}'
    try:
        _spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
            object(),  # type: ignore[arg-type]
            model_id="seedance-2.5",
            prompt="keep this character consistent",
            parameters={
                **_seedance_params(),
                "reference_image_urls": ["https://cdn.example/subject.png"],
            },
        )
    finally:
        settings.generation_pricing_json = previous

    assert clean["reference_image_urls"] == ["https://cdn.example/subject.png"]
    assert seconds == 5
    assert unit_price == Decimal("10")
    assert cost == Decimal("50.00")


@pytest.mark.asyncio
async def test_legacy_video_reference_alias_is_normalized_and_doubled() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = '{"seedance-2.5":{"per_second":10}}'
    try:
        _spec, clean, cost, seconds, unit_price = await GenerationService.prepare_request(
            object(),  # type: ignore[arg-type]
            model_id="seedance-2.5",
            prompt="use legacy motion reference",
            parameters={
                **_seedance_params(),
                "video_reference_urls": ["https://cdn.example/legacy-motion.mp4"],
            },
        )
    finally:
        settings.generation_pricing_json = previous

    assert clean["reference_video_urls"] == ["https://cdn.example/legacy-motion.mp4"]
    assert seconds == 5
    assert unit_price == Decimal("20")
    assert cost == Decimal("100.00")
