from decimal import Decimal

import pytest

from app.services.model_catalog import InvalidModelParametersError, ModelCatalog, UnknownModelError
from app.services.trending_model_catalog import (
    ACTIVE_NEW_WORK_MODEL_IDS,
    TRENDING_PUBLIC_MODEL_ORDER,
)


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
            "wan-2.7-r2v",
            {"prompt": "legacy route", "duration": 5},
        )


def test_hidden_auto_route_target_can_still_execute_from_router() -> None:
    assert "wan-2.7-t2v" not in TRENDING_PUBLIC_MODEL_ORDER
    assert "wan-2.7-t2v" in ACTIVE_NEW_WORK_MODEL_IDS

    spec, params, cost, seconds, _unit = ModelCatalog.prepare(
        "wan-2.7-t2v",
        {"prompt": "public Wan product resolved to text video", "duration": 5},
    )

    assert spec.id == "wan-2.7-t2v"
    assert params["prompt"] == "public Wan product resolved to text video"
    assert seconds == 5
    assert cost > Decimal("0")


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


def test_grok_extend_uses_provider_extension_seconds_for_billing() -> None:
    with pytest.raises(InvalidModelParametersError, match="prompt"):
        ModelCatalog.prepare(
            "grok-video-extend",
            {
                "task_id": "task_grok_123",
                "extend_at": 2,
                "extend_times": "6",
            },
        )

    with pytest.raises(InvalidModelParametersError, match="extend_at"):
        ModelCatalog.prepare(
            "grok-video-extend",
            {
                "task_id": "task_grok_123",
                "prompt": "continue the camera move",
                "extend_times": "6",
            },
        )

    with pytest.raises(InvalidModelParametersError, match="6 or 10"):
        ModelCatalog.prepare(
            "grok-video-extend",
            {
                "task_id": "task_grok_123",
                "prompt": "continue the camera move",
                "extend_at": 2,
                "extend_times": "8",
            },
        )

    _spec, params, cost, seconds, _unit = ModelCatalog.prepare(
        "grok-video-extend",
        {
            "task_id": "task_grok_123",
            "prompt": "continue the camera move",
            "extend_at": 2,
            "extend_times": "6",
        },
    )
    assert params["extend_times"] == "6"
    assert seconds == 6
    assert cost == Decimal("60.00")
