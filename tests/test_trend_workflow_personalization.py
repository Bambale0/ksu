"""Workflow personalization follows the same literal-input guarantees as v1."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.trend_workflows import TrendWorkflowService


def _recipe() -> dict:
    return TrendWorkflowService.normalize_recipe("Personalized photo", {
        "schema_version": 2, "workflow_type": "sequential_photo_video",
        "preview_url": "https://example.invalid/preview.jpg",
        "steps": [
            {"id": "photo", "kind": "image", "title": "Photo", "instructions": "Check your details",
             "preview_url": "https://example.invalid/step-1.jpg",
             "model_id": "nano-banana-pro", "prompt": "Title: {{caption}}; age={{age}}; date={{birthday}}; sign={{sign}}",
             "parameters": {"resolution": "1K", "aspect_ratio": "9:16"},
             "inputs": [
                 {"id": "caption", "type": "text", "label": "Caption", "help": "Your exact text", "required": True, "order": 0},
                 {"id": "age", "type": "number", "label": "Age", "help": "Age in years", "required": True, "order": 1},
                 {"id": "birthday", "type": "date", "label": "Date", "help": "Calendar date", "required": True, "order": 2},
                 {"id": "sign", "type": "select", "label": "Sign", "help": "Choose a sign", "required": True, "order": 3, "options": ["Libra", "Aries"]},
             ]},
            {"id": "video", "kind": "video", "title": "Video", "instructions": "Animate",
             "preview_url": "https://example.invalid/step-2.jpg",
             "model_id": "seedance-2.5", "prompt": "Animate @Image1", "inputs": [],
             "parameters": {"duration": 5, "resolution": "720p", "aspect_ratio": "9:16"},
             "bindings": [{"from": "photo.output_image", "to": "reference_image_urls"}]},
        ],
    })


def _values() -> dict:
    return {"caption": "Happy birthday", "age": "31", "birthday": "2026-10-27", "sign": "Libra"}


@pytest.mark.asyncio
async def test_required_personalization_does_not_hide_template_from_public_catalog() -> None:
    recipe = _recipe()
    item = SimpleNamespace(id=uuid4(), title="Personalized photo", created_at=datetime.now(timezone.utc))
    view = await TrendWorkflowService.public_trend_view(AsyncMock(), item, recipe)
    assert view["workflow_type"] == "sequential_photo_video"
    assert len(view["steps"][0]["inputs"]) == 4
    assert [step["preview_url"] for step in view["steps"]] == [
        "https://example.invalid/step-1.jpg",
        "https://example.invalid/step-2.jpg",
    ]
    assert "prompt" not in view["steps"][0]
    assert "values" not in view["steps"][0]
    assert view["steps"][0]["quote"]["cost_rox"]


def test_personalization_is_inserted_once_not_reexpanded() -> None:
    recipe = _recipe()
    values = {**_values(), "caption": r"Literal {{age}} \1"}
    prompt, _ = TrendWorkflowService._step_request(recipe, recipe["steps"][0], {"values": values})
    assert r"Title: Literal {{age}} \1; age=31" in prompt


@pytest.mark.parametrize("key,value", [
    ("birthday", "2026-02-31"), ("birthday", "2026-13-01"),
    ("age", "NaN"), ("age", "Infinity"), ("age", "-Infinity"),
    ("caption", "   "), ("caption", "x" * 161), ("caption", {"unexpected": "object"}),
])
def test_invalid_personalization_is_rejected_before_generation(key, value) -> None:
    recipe = _recipe()
    with pytest.raises(ValueError):
        TrendWorkflowService._step_request(recipe, recipe["steps"][0], {"values": {**_values(), key: value}})
