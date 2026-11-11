"""Kling 4 curated two-photo + one administrator-pinned video regression."""
from __future__ import annotations

import pytest

from app.services.trends import TrendRecipeError, TrendService

VIDEO = "https://roxy.example/uploads/refs/video/admin-owned-example.mp4"
IMAGES = [
    "https://roxy.example/uploads/refs/image/visitor-1.jpg",
    "https://roxy.example/uploads/refs/image/visitor-2.jpg",
]


def recipe(*, model: str = "kling-4.0", **overrides):
    return {
        "model_id": model,
        "prompt": "@image_1 and @image_2 follow @video_1",
        "media_type": "video",
        "preview_url": "https://roxy.example/preview.jpg",
        "input_mode": "image",
        "min_references": 2,
        "max_references": 2,
        "parameters": {"duration": 5, "aspect_ratio": "9:16", "resolution": "720p"},
        "template_video_url": VIDEO,
        **overrides,
    }


def test_kling_template_preserves_pinned_video_and_two_user_photo_slots():
    normalized = TrendService.normalize_recipe("Two people", recipe())
    assert normalized["template_video_url"] == VIDEO
    assert normalized["min_references"] == normalized["max_references"] == 2
    assert normalized["video_reference_count"] == 0
    params = TrendService._parameters_with_references(normalized, IMAGES)
    assert params["image_urls"] == IMAGES
    assert params["video_urls"] == [VIDEO]
    assert "template_video_url" not in params


@pytest.mark.parametrize("updates", [
    {"min_references": 1},
    {"max_references": 3},
    {"input_mode": "none", "min_references": 0, "max_references": 0},
    {"model_id": "kling-4.0-keyframe"},
    {"model_id": "seedance-2.5"},
    {"parameters": {"duration": 5, "resolution": "720p"}},
    {"parameters": {"duration": 5, "aspect_ratio": "auto", "resolution": "720p"}},
    {"parameters": {"duration": 5, "aspect_ratio": "9:16", "video_urls": [VIDEO]}},
])
def test_pinned_template_rejects_other_models_or_not_exactly_two_photos(updates):
    with pytest.raises(TrendRecipeError):
        TrendService.normalize_recipe("Invalid", recipe(**updates))


def test_pinned_template_cannot_change_private_quality_or_ratio():
    normalized = TrendService.normalize_recipe("Locked", recipe())
    with pytest.raises(TrendRecipeError):
        TrendService._parameters_with_references(normalized, IMAGES, aspect_ratio="16:9", require_aspect_ratio=True)
    with pytest.raises(TrendRecipeError):
        TrendService._parameters_with_references(normalized, IMAGES, resolution="1080p", require_aspect_ratio=True)
    assert TrendService._parameters_with_references(normalized, IMAGES, require_aspect_ratio=True)["aspect_ratio"] == "9:16"


def test_non_pinned_kling_remains_user_video_capable_outside_trends():
    normalized = TrendService.normalize_recipe("Normal template", recipe(template_video_url=None))
    assert normalized["template_video_url"] is None
    assert "video_urls" not in TrendService._parameters_with_references(normalized, IMAGES)
