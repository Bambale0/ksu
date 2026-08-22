from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.v1.generation_actions import (
    DeriveGenerationRequest,
    derive_generation,
    generation_action_context,
)
from app.core.config import settings
from app.db.models import Generation, User
from app.db.session import SessionFactory
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


def _telegram_id() -> int:
    return random.randint(8_100_000_000_000, 8_999_999_999_999)


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


def test_trend_recipe_references_are_never_exposed_to_derivative_context() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro", action_type="trend")
    generation.input_url = "https://secret.example/input.png"
    generation.parameters = {
        **generation.parameters,
        "image_input": ["https://secret.example/reference.png"],
    }

    assert GenerationActionService.parent_references(generation) == ([], [])


def test_animate_defaults_to_grok_i2v_like_lena() -> None:
    generation = _generation(media_type="image", model_id="gpt-image-2-t2i")
    assert GenerationActionService.default_model_id(generation, "animate") == "grok-video-i2v"


def test_edit_candidates_exclude_non_edit_image_operations() -> None:
    generation = _generation(media_type="image", model_id="nano-banana-pro")
    candidate_ids = {item["id"] for item in GenerationActionService.public_candidates(generation, "edit")}
    assert "seedream-5-pro-layers" not in candidate_ids
    assert "nano-banana-pro" in candidate_ids


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
    parameters, input_url = GenerationActionService.adapt_references(
        generation,
        target,
        {"aspect_ratio": "1:1"},
    )
    assert parameters["input_urls"] == [
        "https://cdn.example/ref-a.png",
        "https://cdn.example/ref-b.png",
        "https://cdn.example/input.png",
    ]
    assert input_url == "https://cdn.example/input.png"


def test_repeat_preserves_seedance25_reference_mode_without_inventing_first_frame() -> None:
    generation = _generation(media_type="video", model_id="seedance-2.5")
    generation.parameters = {
        **generation.parameters,
        "reference_image_urls": ["https://cdn.example/subject.png"],
        "reference_video_urls": ["https://cdn.example/style.mp4"],
        "duration": 5,
        "resolution": "720p",
        "aspect_ratio": "adaptive",
    }

    target = ModelCatalog.get("seedance-2.5")
    parameters, _input_url = GenerationActionService.adapt_references(
        generation,
        target,
        GenerationActionService.reusable_parameters(generation, target.id),
    )

    assert parameters["reference_image_urls"] == ["https://cdn.example/subject.png"]
    assert parameters["reference_video_urls"] == ["https://cdn.example/style.mp4"]
    assert "first_frame_url" not in parameters


def test_repeat_preserves_seedance20_hybrid_frame_and_reference_mode() -> None:
    generation = _generation(media_type="video", model_id="seedance-2.0")
    generation.parameters = {
        **generation.parameters,
        "first_frame_url": "https://cdn.example/first.png",
        "reference_image_urls": ["https://cdn.example/subject.png"],
        "duration": 5,
        "resolution": "720p",
        "aspect_ratio": "16:9",
    }

    target = ModelCatalog.get("seedance-2.0")
    parameters, _input_url = GenerationActionService.adapt_references(
        generation,
        target,
        GenerationActionService.reusable_parameters(generation, target.id),
    )

    assert parameters["first_frame_url"] == "https://cdn.example/first.png"
    assert parameters["reference_image_urls"] == ["https://cdn.example/subject.png"]


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


def test_telegram_audio_keyboard_has_only_general_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")
    generation = _generation(media_type="audio", model_id="suno-v5.5")
    keyboard = _generation_keyboard(generation, generation.result_url)
    assert keyboard is not None
    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert "🔄 Ещё вариант" in labels
    assert "✏️ Новый промпт" in labels
    assert "⚙️ Изменить параметры" in labels
    assert "📤 Опубликовать" in labels
    assert "✨ Ремикс" not in labels


@pytest.mark.asyncio
async def test_action_context_hides_trend_prompt_and_reference_recipe() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Trend owner")
        session.add(user)
        await session.flush()
        generation = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="server-only trend recipe",
            input_url="https://secret.example/input.png",
            result_url="https://cdn.example/result.png",
            cost_rox=Decimal("25.00"),
            provider="kie",
            parameters={
                "_model_id": "nano-banana-pro",
                "_media_type": "image",
                "image_input": ["https://secret.example/reference.png"],
            },
            action_type="trend",
        )
        session.add(generation)
        await session.commit()

        context = await generation_action_context(
            generation.id,
            user,
            session,
            action="remix",
        )

        assert context["generation"]["prompt"] == ""
        assert context["generation"]["prompt_hidden"] is True
        assert context["source_references"] == {"images": [], "videos": []}
        assert context["source_url"] == "https://cdn.example/result.png"


@pytest.mark.asyncio
async def test_action_context_is_strictly_owner_scoped() -> None:
    async with SessionFactory() as session:
        owner = User(telegram_id=_telegram_id(), first_name="Owner")
        stranger = User(telegram_id=_telegram_id(), first_name="Stranger")
        session.add_all([owner, stranger])
        await session.flush()
        generation = Generation(
            user_id=owner.id,
            kind="text_to_image",
            status="succeeded",
            prompt="private",
            result_url="https://cdn.example/private.png",
            cost_rox=Decimal("25.00"),
            provider="kie",
            parameters={"_model_id": "nano-banana-pro", "_media_type": "image"},
        )
        session.add(generation)
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await generation_action_context(
                generation.id,
                stranger,
                session,
                action="repeat",
            )
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_remix_submit_persists_explicit_parent_lineage(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Remixer")
        session.add(user)
        await session.flush()
        parent = Generation(
            user_id=user.id,
            kind="text_to_image",
            status="succeeded",
            prompt="old prompt",
            result_url="https://cdn.example/parent.png",
            cost_rox=Decimal("25.00"),
            provider="kie",
            parameters={"_model_id": "nano-banana-pro", "_media_type": "image"},
        )
        session.add(parent)
        await session.commit()

        captured: dict[str, object] = {}

        async def fake_create(
            _cls,
            target_session,
            _redis,
            **kwargs,
        ):
            captured.update(kwargs)
            child = Generation(
                id=uuid.uuid4(),
                user_id=kwargs["user_id"],
                kind="image_edit",
                status="queued",
                prompt=kwargs["prompt"],
                input_url=kwargs["input_url"],
                cost_rox=Decimal("25.00"),
                provider="kie",
                parameters={"_model_id": kwargs["model_id"]},
                parent_generation_id=kwargs["parent_generation_id"],
                action_type=kwargs["action_type"],
            )
            target_session.add(child)
            await target_session.flush()
            return child

        monkeypatch.setattr(
            "app.api.v1.generation_actions.GenerationService.create",
            classmethod(fake_create),
        )

        result = await derive_generation(
            parent.id,
            "remix",
            DeriveGenerationRequest(
                model_id="nano-banana-pro",
                prompt="make the dress blue",
                parameters={},
            ),
            user,
            session,
            object(),  # type: ignore[arg-type]
        )

        assert captured["parent_generation_id"] == parent.id
        assert captured["action_type"] == "remix"
        assert captured["input_url"] == parent.result_url
        assert captured["prompt"] == "make the dress blue"
        assert result["parent_generation_id"] == str(parent.id)
        assert result["action_type"] == "remix"


@pytest.mark.asyncio
async def test_parameters_action_normalizes_lineage_to_repeat(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Repeat")
        session.add(user)
        await session.flush()
        parent = Generation(
            user_id=user.id,
            kind="text_to_video",
            status="succeeded",
            prompt="same motion prompt",
            result_url="https://cdn.example/parent.mp4",
            cost_rox=Decimal("25.00"),
            provider="kie",
            parameters={
                "_model_id": "grok-video-1.5",
                "_media_type": "video",
                "aspect_ratio": "16:9",
                "duration": 8,
                "resolution": "480p",
            },
        )
        session.add(parent)
        await session.commit()

        captured: dict[str, object] = {}

        async def fake_create(_cls, target_session, _redis, **kwargs):
            captured.update(kwargs)
            child = Generation(
                id=uuid.uuid4(),
                user_id=kwargs["user_id"],
                kind="text_to_video",
                status="queued",
                prompt=kwargs["prompt"],
                cost_rox=Decimal("25.00"),
                provider="kie",
                parameters={"_model_id": kwargs["model_id"]},
                parent_generation_id=kwargs["parent_generation_id"],
                action_type=kwargs["action_type"],
            )
            target_session.add(child)
            await target_session.flush()
            return child

        monkeypatch.setattr(
            "app.api.v1.generation_actions.GenerationService.create",
            classmethod(fake_create),
        )

        result = await derive_generation(
            parent.id,
            "parameters",
            DeriveGenerationRequest(
                model_id="grok-video-1.5",
                prompt="same motion prompt",
                parameters={"aspect_ratio": "9:16"},
            ),
            user,
            session,
            object(),  # type: ignore[arg-type]
        )

        assert captured["parent_generation_id"] == parent.id
        assert captured["action_type"] == "repeat"
        assert captured["prompt"] == "same motion prompt"
        assert result["action_type"] == "repeat"
