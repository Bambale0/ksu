from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import Generation
from app.services.generation_actions import GenerationActionService
from app.services.model_catalog import ModelCatalog
from app.workers.notifications import _generation_keyboard


def _generation(
    *,
    media_type: str,
    model_id: str,
    action_type: str | None = None,
    result_url: str | None = None,
) -> Generation:
    extension = "mp4" if media_type == "video" else "mp3" if media_type == "audio" else "png"
    return Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="music" if media_type == "audio" else media_type,
        status="succeeded",
        prompt="portrait in soft light",
        result_url=result_url or f"https://cdn.example/result.{extension}",
        cost_rox=Decimal("25.00"),
        parameters={
            "_model_id": model_id,
            "_media_type": media_type,
            "_model_title": model_id,
        },
        action_type=action_type,
    )


def _action_ids(generation: Generation) -> list[str]:
    return [item.id for item in GenerationActionService.available_actions(generation)]


def test_image_generation_exposes_full_lena_action_layer() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    assert _action_ids(generation) == ["remix", "repeat", "edit", "animate", "publish"]


def test_video_and_audio_use_general_post_generation_layer() -> None:
    video = _generation(media_type="video", model_id="grok-video-1.5")
    audio = _generation(media_type="audio", model_id="suno-v5.5")

    expected = ["repeat", "new_prompt", "parameters", "publish"]
    assert _action_ids(video) == expected
    assert _action_ids(audio) == expected


def test_failed_or_unfinished_generation_has_no_derivative_actions() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    generation.status = "failed"
    assert GenerationActionService.available_actions(generation) == []


def test_admin_trend_prompt_cannot_be_reconstructed() -> None:
    image = _generation(media_type="image", model_id="nano-banana-pro", action_type="trend")
    video = _generation(media_type="video", model_id="grok-video-1.5", action_type="trend")

    assert _action_ids(image) == ["remix", "edit", "animate", "publish"]
    assert _action_ids(video) == ["publish"]


def test_animate_defaults_to_grok_i2v_like_lena() -> None:
    generation = _generation(media_type="image", model_id="gpt-image-2-t2i")
    assert GenerationActionService.default_model_id(generation, "animate") == "grok-video-i2v"


def test_repeat_prefers_current_model_and_preserves_compatible_references() -> None:
    generation = _generation(media_type="image", model_id="gpt-image-2-i2i")
    generation.input_url = "https://cdn.example/input.png"
    generation.parameters = {
        **generation.parameters,
        "input_urls": ["https://cdn.example/ref-a.png", "https://cdn.example/ref-b.png"],
        "aspect_ratio": "1:1",
    }

    assert GenerationActionService.default_model_id(generation, "repeat") == "gpt-image-2-i2i"
    target = ModelCatalog.get("gpt-image-2-i2i")
    parameters, input_url = GenerationActionService.adapt_references(generation, target, {"aspect_ratio": "1:1"})
    assert parameters["input_urls"] == [
        "https://cdn.example/ref-a.png",
        "https://cdn.example/ref-b.png",
        "https://cdn.example/input.png",
    ]
    assert input_url == "https://cdn.example/input.png"


def test_style_edit_prompt_changes_only_requested_focus() -> None:
    prompt = GenerationActionService.edit_prompt("long red hair", "hair")
    assert "Change ONLY the hairstyle" in prompt
    assert "long red hair" in prompt
    assert "Keep the person's identity" in prompt


def test_telegram_image_keyboard_contains_action_deep_links(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    keyboard = _generation_keyboard(generation, generation.result_url)
    assert keyboard is not None

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    labels = [button.text for button in buttons]
    for label in ("✨ Ремикс", "🔁 Ещё вариант", "💅 Изменить образ", "🎬 Оживить", "📤 Опубликовать"):
        assert label in labels
    assert "📥 Скачать оригинал" in labels
    assert "🚀 Открыть в ROXY" in labels

    remix = next(button for button in buttons if button.text == "✨ Ремикс")
    assert remix.web_app is not None
    assert "route=generation-action" in remix.web_app.url
    assert f"generation={generation.id}" in remix.web_app.url
    assert "action=remix" in remix.web_app.url


def test_telegram_video_keyboard_does_not_offer_image_only_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    generation = _generation(media_type="video", model_id="grok-video-1.5")
    keyboard = _generation_keyboard(generation, generation.result_url)
    assert keyboard is not None
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "🔄 Ещё вариант" in labels
    assert "✏️ Новый промпт" in labels
    assert "⚙️ Изменить параметры" in labels
    assert "🎬 Оживить" not in labels
    assert "💅 Изменить образ" not in labels
