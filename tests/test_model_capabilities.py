from decimal import Decimal

import pytest

from app.services.model_catalog import InvalidModelParametersError, ModelCatalog, UnknownModelError
from app.services.trending_model_catalog import TRENDING_PUBLIC_MODEL_ORDER


def test_catalog_contains_exact_trending_public_model_set() -> None:
    models = ModelCatalog.list()
    ids = [item["id"] for item in models]
    families = {item["family"] for item in models}

    assert ids == list(TRENDING_PUBLIC_MODEL_ORDER)
    assert len(ids) == 23
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


def test_removed_legacy_model_cannot_start_new_work() -> None:
    with pytest.raises(UnknownModelError, match="Inactive generation model"):
        ModelCatalog.prepare(
            "wan-2.7-t2v",
            {"prompt": "legacy route", "duration": 5},
        )


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


def test_current_wan_photo_model_accepts_edit_references() -> None:
    spec, params, cost, seconds, _unit = ModelCatalog.prepare(
        "wan-2.7-image-pro",
        {
            "prompt": "keep composition and change the product color",
            "input_urls": ["https://example.com/source.png"],
            "n": 1,
            "resolution": "2K",
        },
    )
    assert spec.media_type == "image"
    assert spec.operation == "generate_or_edit"
    assert params["input_urls"] == ["https://example.com/source.png"]
    assert seconds is None
    assert cost > Decimal("0")


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
