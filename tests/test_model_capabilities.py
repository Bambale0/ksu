from decimal import Decimal

import pytest

from app.services.model_catalog import InvalidModelParametersError, ModelCatalog


def test_catalog_contains_all_requested_families_and_variants() -> None:
    models = ModelCatalog.list()
    families = {item["family"] for item in models}
    assert {"nanobanana", "seedream", "gpt-image", "wan", "seedance", "kling", "grok"} <= families
    assert len(models) >= 35


def test_seedance_reference_and_frame_modes_are_mutually_exclusive() -> None:
    with pytest.raises(InvalidModelParametersError, match="mutually exclusive"):
        ModelCatalog.prepare(
            "seedance-2.5",
            {
                "prompt": "scene",
                "duration": 5,
                "first_frame_url": "https://example.com/first.png",
                "reference_video_urls": ["https://example.com/ref.mp4"],
            },
        )


def test_wan_i2v_supports_video_continuation() -> None:
    _spec, params, cost, seconds, _unit = ModelCatalog.prepare(
        "wan-2.7-i2v",
        {
            "prompt": "continue naturally",
            "first_clip_url": "https://example.com/source.mp4",
            "duration": 6,
        },
    )
    assert params["first_clip_url"].endswith("source.mp4")
    assert seconds == 6
    assert cost == Decimal("72.00")


def test_grok_extend_requires_explicit_billed_seconds() -> None:
    with pytest.raises(InvalidModelParametersError, match="duration"):
        ModelCatalog.prepare(
            "grok-video-extend",
            {"task_id": "task_grok_123", "extend_times": "6"},
        )

    _spec, _params, cost, seconds, _unit = ModelCatalog.prepare(
        "grok-video-extend",
        {"task_id": "task_grok_123", "extend_times": "6"},
        billing_seconds=6,
    )
    assert seconds == 6
    assert cost == Decimal("60.00")


def test_kling_motion_rejects_multiple_reference_images() -> None:
    with pytest.raises(InvalidModelParametersError, match="exactly one input image"):
        ModelCatalog.prepare(
            "kling-motion-2.6",
            {
                "prompt": "motion",
                "input_urls": ["https://example.com/a.png", "https://example.com/b.png"],
                "video_urls": ["https://example.com/a.mp4"],
            },
            billing_seconds=5,
        )
