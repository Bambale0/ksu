from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.private_repeat_links import (
    apply_repeat_reference_parameters,
    generation_id_from_repeat_token,
    public_repeat_descriptor,
    repeat_token,
    sanitize_repeat_recipe,
)

ROOT = Path(__file__).resolve().parents[1]


def test_repeat_token_is_short_signed_and_tamper_evident(monkeypatch) -> None:
    monkeypatch.setattr(settings, "admin_security_key", "x" * 64)
    generation_id = uuid.uuid4()

    token = repeat_token(generation_id)

    assert generation_id_from_repeat_token(token) == generation_id
    assert len(f"repeat_{token}") <= 64
    replacement = "A" if token[-1] != "A" else "B"
    assert generation_id_from_repeat_token(token[:-1] + replacement) is None


def test_private_repeat_recipe_never_exposes_owner_media() -> None:
    recipe = sanitize_repeat_recipe(
        {
            "model_id": "nano-banana-2",
            "prompt": "portrait in neon",
            "input_url": "https://private.example/source.png",
            "billing_seconds": 10,
            "parameters": {
                "aspect_ratio": "9:16",
                "resolution": "2K",
                "seed": 42,
                "reference_images": ["https://private.example/ref.png"],
                "reference_video_urls": ["https://private.example/ref.mov"],
                "first_frame_url": "/uploads/refs/private-first.png",
                "provider_asset": {"url": "https://private.example/provider.png"},
            },
        }
    )

    assert recipe == {
        "model_id": "nano-banana-2",
        "prompt": "portrait in neon",
        "input_url": None,
        "billing_seconds": 10,
        "parameters": {
            "aspect_ratio": "9:16",
            "resolution": "2K",
            "seed": 42,
        },
        "references_required": True,
        "reference_fields": ["input_url", "reference_images", "reference_video_urls", "first_frame_url"],
    }

    public = public_repeat_descriptor(recipe)
    assert public == {
        "model_id": "nano-banana-2",
        "references_required": True,
        "reference_fields": ["input_url", "reference_images", "reference_video_urls", "first_frame_url"],
    }
    serialized = str(public)
    assert "portrait in neon" not in serialized
    assert "2K" not in serialized
    assert "seed" not in serialized
    assert "private.example" not in serialized


def test_private_repeat_recipient_can_only_supply_owned_reference_media() -> None:
    recipe = sanitize_repeat_recipe(
        {
            "model_id": "reference-model",
            "prompt": "SERVER_ONLY_SENTINEL_PROMPT",
            "input_url": "https://owner.example/source.png",
            "billing_seconds": 8,
            "parameters": {"resolution": "2K", "seed": 777},
        }
    )

    merged = apply_repeat_reference_parameters(
        recipe,
        {"input_url": "https://recipient.example/upload.png"},
    )
    assert merged == {
        "model_id": "reference-model",
        "prompt": "SERVER_ONLY_SENTINEL_PROMPT",
        "input_url": "https://recipient.example/upload.png",
        "billing_seconds": 8,
        "parameters": {"resolution": "2K", "seed": 777},
    }

    with pytest.raises(ValueError, match="only reference uploads"):
        apply_repeat_reference_parameters(recipe, {"resolution": "4K"})


def test_private_repeat_api_does_not_publish_or_return_source_identity() -> None:
    source = (ROOT / "app/api/v1/generation_repeat_links.py").read_text(encoding="utf-8")

    assert '@router.post("/generations/{generation_id}/repeat-link")' in source
    assert '@router.get("/generation-repeat-links/{token}")' in source
    assert '@router.post("/generation-repeat-links/{token}/quote")' in source
    assert '@router.post("/generation-repeat-links/{token}/launch", status_code=202)' in source
    assert "generation.user_id != user.id" in source
    assert "public_repeat_descriptor(recipe)" in source
    assert "_repeat_generation_request(recipe, payload)" in source
    assert "mini_app_deep_link(payload)" in source
    assert 'payload = f"repeat_{token}"' in source
    assert "FeedService.publish" not in source
    assert "publication_scope =" not in source
    assert '"generation_id"' not in source
    assert '"result_url"' not in source


def test_private_repeat_frontend_never_receives_or_posts_hidden_recipe() -> None:
    gate = (ROOT / "frontend/mini-app/components/app-entry-gate.tsx").read_text(encoding="utf-8")
    flow = (ROOT / "frontend/mini-app/components/private-repeat-startapp.tsx").read_text(encoding="utf-8")
    repeat_api = (ROOT / "frontend/mini-app/lib/private-repeat-api.ts").read_text(encoding="utf-8")
    repeat_page = (ROOT / "frontend/mini-app/app/repeat/page.tsx").read_text(encoding="utf-8")
    button = (ROOT / "frontend/mini-app/components/private-repeat-link-ux.tsx").read_text(encoding="utf-8")
    onboarding = (ROOT / "frontend/mini-app/components/user-onboarding.tsx").read_text(encoding="utf-8")
    page = (ROOT / "frontend/mini-app/app/page.tsx").read_text(encoding="utf-8")

    assert "PRIVATE_REPEAT_LINK" in gate
    assert 'kind: "repeat"' in gate
    assert "/mini-app/repeat/?token=" in gate
    assert "current.searchParams.has(\"route\")" in gate
    assert "PrivateRepeatStartApp" in repeat_page
    assert "TOKEN_RE" in repeat_page
    assert "privateRepeatApi.resolve(token)" in flow
    assert "privateRepeatApi.quote(token, parameters)" in flow
    assert "privateRepeatApi.launch(token, parameters)" in flow
    assert "api.quote(" not in flow
    assert "api.create(" not in flow
    assert "RecreateGenerationPayload" not in flow
    assert "nextDescriptor.prompt" not in flow
    assert "nextDescriptor.parameters" not in flow
    assert "nextDescriptor.billing_seconds" not in flow
    assert "prompt:" not in repeat_api
    assert "billing_seconds" not in repeat_api
    assert "/generation-repeat-links/${encodeURIComponent(token)}/quote" in repeat_api
    assert "/generation-repeat-links/${encodeURIComponent(token)}/launch" in repeat_api
    assert "Промпт и настройки исходной работы скрыты" in flow
    assert "не загружаются в приложение" in flow
    assert 'field.control === "file" || field.control === "files"' in flow
    assert '<span className="label">Описание</span>' not in flow
    assert "Новая работа останется приватной" in flow
    assert "Скопировать ссылку на повтор" in button
    assert "работа осталась приватной" in button
    assert "privateRepeatApi.createLink(generationId)" in button
    assert "history-card .private-repeat-link-history" not in button
    assert "repeat_" in onboarding
    assert "<PrivateRepeatLinkUx />" in page
