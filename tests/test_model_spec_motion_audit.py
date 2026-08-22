from __future__ import annotations

import pytest

from app.services.model_catalog import InvalidModelParametersError, ModelCatalog


@pytest.mark.parametrize("model_id", ["kling-motion-2.6", "kling-motion-3.0"])
def test_kling_motion_image_orientation_is_limited_to_ten_seconds(model_id: str) -> None:
    params = {
        "prompt": "transfer the dance naturally",
        "input_urls": ["https://cdn.example/person.png"],
        "video_urls": ["https://cdn.example/motion.mp4"],
        "mode": "720p",
        "character_orientation": "image",
    }

    _spec, _clean, _cost, seconds, _unit = ModelCatalog.prepare(
        model_id, params, billing_seconds=10
    )
    assert seconds == 10

    with pytest.raises(InvalidModelParametersError, match="up to 10 seconds"):
        ModelCatalog.prepare(model_id, params, billing_seconds=11)


@pytest.mark.parametrize("model_id", ["kling-motion-2.6", "kling-motion-3.0"])
def test_kling_motion_video_orientation_supports_up_to_thirty_seconds(model_id: str) -> None:
    params = {
        "prompt": "transfer the performance",
        "input_urls": ["https://cdn.example/person.png"],
        "video_urls": ["https://cdn.example/motion.mp4"],
        "mode": "1080p",
        "character_orientation": "video",
    }
    _spec, _clean, _cost, seconds, _unit = ModelCatalog.prepare(
        model_id, params, billing_seconds=30
    )
    assert seconds == 30


@pytest.mark.parametrize("model_id", ["kling-motion-2.6", "kling-motion-3.0"])
def test_kling_motion_prompt_limit_is_enforced_before_billing(model_id: str) -> None:
    params = {
        "prompt": "x" * 2501,
        "input_urls": ["https://cdn.example/person.png"],
        "video_urls": ["https://cdn.example/motion.mp4"],
        "mode": "720p",
        "character_orientation": "image",
    }
    with pytest.raises(InvalidModelParametersError, match="2500"):
        ModelCatalog.prepare(model_id, params, billing_seconds=5)
