from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.api.v1.generations import _generation_view
from app.api.v1.trends import RunTrendRequest
from app.db.models import Generation
from app.services.trends import TrendRecipeError, TrendService

ROOT = Path(__file__).resolve().parents[1]


def test_run_request_accepts_only_reference_urls() -> None:
    assert set(RunTrendRequest.model_fields) == {"reference_urls"}


def test_recipe_normalizes_curated_fields() -> None:
    recipe = TrendService.normalize_recipe(
        "Editorial",
        {
            "description": "Portrait template",
            "model_id": "nano-banana-pro",
            "prompt": "curated template text",
            "preview_url": "https://cdn.example.invalid/trend.jpg",
            "media_type": "image",
            "input_mode": "image",
            "min_references": 1,
            "max_references": 4,
            "parameters": {"aspect_ratio": "1:1", "resolution": "1K"},
            "tags": ["Portrait", "portrait", "editorial"],
        },
    )
    assert recipe["model_id"] == "nano-banana-pro"
    assert recipe["input_mode"] == "image"
    assert recipe["tags"] == ["portrait", "editorial"]


def test_non_http_reference_urls_are_rejected() -> None:
    for value in ("blob:https://miniapp.invalid/123", "data:image/png;base64,AAAA"):
        with pytest.raises(TrendRecipeError):
            TrendService._safe_http_url(value, field="reference_url")


def test_trend_generation_view_hides_curated_recipe() -> None:
    now = datetime.now(UTC)
    generation = Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="generate_or_edit",
        prompt="curated template text",
        cost_rox=Decimal("20.00"),
        provider="kie",
        status="queued",
        parameters={
            "prompt": "curated template text",
            "aspect_ratio": "1:1",
            "_model_id": "nano-banana-pro",
        },
        action_type="trend",
        created_at=now,
        updated_at=now,
    )
    view = _generation_view(generation)
    assert view["prompt"] == ""
    assert view["settings"] == {}
    assert view["prompt_hidden"] is True
    assert view["prompt_actions_allowed"] is False
    assert "curated template text" not in repr(view)


def test_trends_mini_app_posts_reference_urls_only() -> None:
    source = (ROOT / "app/web/mini_app/trends.js").read_text(encoding="utf-8")
    assert "JSON.stringify({ reference_urls: uploadedUrls })" in source
    assert "innerHTML" not in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source
    assert "eval(" not in source
    assert "new Function" not in source


def test_bot_exposes_trends_and_prompts_commands() -> None:
    source = (ROOT / "app/bot/handlers/trends.py").read_text(encoding="utf-8")
    assert 'Command("trends")' in source
    assert 'Command("prompts")' in source
