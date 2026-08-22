from decimal import Decimal

import pytest

from app.core.config import settings
from app.services.model_catalog import InvalidModelParametersError, ModelCatalog


def test_requested_model_families_are_exposed() -> None:
    families = {item["family"] for item in ModelCatalog.list()}
    assert {
        "nanobanana",
        "seedream",
        "gpt-image",
        "wan",
        "seedance",
        "kling",
        "grok",
        "veo",
        "gemini",
    } <= families


def test_video_price_is_calculated_per_second() -> None:
    spec, _params, cost, seconds, unit_price = ModelCatalog.prepare(
        "seedance-2.0",
        {"prompt": "city at night", "duration": 5},
    )
    assert spec.price_mode == "per_second"
    assert unit_price == Decimal("40")
    assert seconds == 5
    assert cost == Decimal("200.00")


def test_image_price_is_flat() -> None:
    spec, _params, cost, seconds, unit_price = ModelCatalog.prepare(
        "gpt-image-2-t2i",
        {"prompt": "portrait"},
        billing_seconds=99,
    )
    assert spec.price_mode == "flat"
    assert unit_price == Decimal("20")
    assert seconds is None
    assert cost == Decimal("20.00")


def test_kling_motion_requires_reference_video_billing_duration() -> None:
    with pytest.raises(InvalidModelParametersError, match="duration"):
        ModelCatalog.prepare(
            "kling-motion-3.0",
            {
                "prompt": "copy the motion",
                "input_urls": ["https://example.com/a.png"],
                "video_urls": ["https://example.com/a.mp4"],
            },
        )

    _spec, _params, cost, seconds, unit_price = ModelCatalog.prepare(
        "kling-motion-3.0",
        {
            "prompt": "copy the motion",
            "input_urls": ["https://example.com/a.png"],
            "video_urls": ["https://example.com/a.mp4"],
            "character_orientation": "video",
        },
        billing_seconds=12,
    )
    assert seconds == 12
    assert unit_price == Decimal("60")
    assert cost == Decimal("720.00")


def test_kling_motion_enforces_provider_duration_range() -> None:
    with pytest.raises(InvalidModelParametersError, match="Minimum duration is 3s"):
        ModelCatalog.prepare(
            "kling-motion-3.0",
            {
                "prompt": "motion",
                "input_urls": ["https://example.com/a.png"],
                "video_urls": ["https://example.com/a.mp4"],
            },
            billing_seconds=2,
        )


def test_internal_parameters_are_not_forwarded() -> None:
    _spec, params, _cost, _seconds, _unit = ModelCatalog.prepare(
        "nano-banana-2",
        {"prompt": "banana", "_model_id": "evil", "_unit_price_rox": "0"},
    )
    assert params == {"prompt": "banana"}


def test_pricing_can_be_overridden_server_side() -> None:
    previous = settings.generation_pricing_json
    settings.generation_pricing_json = '{"seedance-2.0":{"per_second":"7.25"}}'
    try:
        _spec, _params, cost, seconds, unit_price = ModelCatalog.prepare(
            "seedance-2.0",
            {"prompt": "test", "duration": 4},
        )
    finally:
        settings.generation_pricing_json = previous

    assert unit_price == Decimal("7.25")
    assert seconds == 4
    assert cost == Decimal("29.00")
