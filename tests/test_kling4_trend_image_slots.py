"""Kling 4.0 trend prompt image references must match user upload slots."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.trends import TrendRecipeError, TrendService


def recipe(prompt: str, *, minimum=1, maximum=1, mode="image") -> dict:
    return {
        "model_id": "kling-4.0",
        "media_type": "video",
        "prompt": prompt,
        "description": "Two users",
        "preview_url": "https://cdn.example.invalid/preview.mp4",
        "input_mode": mode,
        "min_references": minimum,
        "max_references": maximum,
        "parameters": {"duration": 5, "resolution": "720p", "aspect_ratio": "16:9"},
    }


@pytest.mark.parametrize("prompt", [
    "@image_1 sings and @image_2 listens",
    "@Image1 sings and @Image2 listens",
    "@IMAGE_1 sings and @IMAGE_2 listens",
])
def test_two_photo_prompt_upgrades_stale_single_slot_recipe(prompt):
    raw = recipe(prompt)
    normalized = TrendService.normalize_recipe("МОИ СЛЕЗЫ", raw)
    assert normalized["input_mode"] == "image"
    assert normalized["min_references"] == 2
    assert normalized["max_references"] == 2
    assert raw["min_references"] == 1  # original draft is not changed


def test_two_photo_prompt_infers_inputs_when_admin_left_mode_none():
    normalized = TrendService.normalize_recipe(
        "МОИ СЛЕЗЫ", recipe("@image_1 and @image_2", mode="none", minimum=0, maximum=0)
    )
    assert normalized["input_mode"] == "image"
    assert normalized["min_references"] == 2
    assert normalized["max_references"] == 2


@pytest.mark.parametrize("prompt", [
    "@image_2 listens", "@image_1 and @image_3",
    "@image_1 and @image_9",
])
def test_invalid_or_out_of_capacity_image_numbering_is_actionable(prompt):
    with pytest.raises(TrendRecipeError, match="фото|ссылк|порядк"):
        TrendService.normalize_recipe("МОИ СЛЕЗЫ", recipe(prompt))


def test_unsupported_video_slot_has_actionable_validation_not_raw_undeclared_reference():
    with pytest.raises(TrendRecipeError, match="видео|видеореференс"):
        TrendService.normalize_recipe("МОИ СЛЕЗЫ", recipe("@image_1 and @video_1"))


def test_non_kling_trend_is_unchanged_by_image_reference_inference():
    raw = recipe("@image_1 and @image_2")
    raw["model_id"] = "seedance-2.0"
    normalized = TrendService.normalize_recipe("Another model", raw)
    assert normalized["min_references"] == 1
    assert normalized["max_references"] == 1


@pytest.mark.asyncio
async def test_validation_uses_two_placeholder_images_before_quote(monkeypatch):
    from app.services.generations import GenerationService
    captured = []

    async def prepare(_session, *, model_id, prompt, parameters, billing_seconds):
        captured.append((model_id, prompt, parameters, billing_seconds))
        return object()

    monkeypatch.setattr(GenerationService, "prepare_template_request", prepare)
    normalized = await TrendService.validate_recipe(
        AsyncMock(), title="МОИ СЛЕЗЫ",
        payload=recipe("@image_1 sings. @image_2 listens."),
    )
    assert normalized["min_references"] == 2
    assert captured[0][0] == "kling-4.0"
    assert captured[0][2]["image_urls"] == [
        "https://example.invalid/trend-reference-1.jpg",
        "https://example.invalid/trend-reference-2.jpg",
    ]
