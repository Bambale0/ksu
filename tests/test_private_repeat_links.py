from __future__ import annotations

from pathlib import Path
import uuid

from app.core.config import settings
from app.services.private_repeat_links import (
    generation_id_from_repeat_token,
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
    }


def test_private_repeat_api_does_not_publish_or_return_source_identity() -> None:
    source = (ROOT / "app/api/v1/generation_repeat_links.py").read_text(encoding="utf-8")

    assert '@router.post("/generations/{generation_id}/repeat-link")' in source
    assert '@router.get("/generation-repeat-links/{token}")' in source
    assert "generation.user_id != user.id" in source
    assert "sanitize_repeat_recipe(raw_recipe)" in source
    assert "mini_app_deep_link(payload)" in source
    assert 'payload = f"repeat_{token}"' in source
    assert "publish" not in source.casefold()
    assert '"generation_id"' not in source
    assert '"result_url"' not in source


def test_private_repeat_frontend_is_independent_from_publication() -> None:
    gate = (ROOT / "frontend/mini-app/components/app-entry-gate.tsx").read_text(encoding="utf-8")
    flow = (ROOT / "frontend/mini-app/components/private-repeat-startapp.tsx").read_text(encoding="utf-8")
    button = (ROOT / "frontend/mini-app/components/private-repeat-link-ux.tsx").read_text(encoding="utf-8")
    onboarding = (ROOT / "frontend/mini-app/components/user-onboarding.tsx").read_text(encoding="utf-8")
    page = (ROOT / "frontend/mini-app/app/page.tsx").read_text(encoding="utf-8")

    assert "PRIVATE_REPEAT_LINK" in gate
    assert 'kind: "repeat"' in gate
    assert "PrivateRepeatStartApp" in gate
    assert "current.searchParams.has(\"route\")" in gate
    assert "privateRepeatApi.resolve(token)" in flow
    assert "Исходная работа остаётся приватной" in flow
    assert "файлы автора не передаются" in flow
    assert "Никакой публикации не происходит" in flow
    assert "Скопировать ссылку на повтор" in button
    assert "работа осталась приватной" in button
    assert "privateRepeatApi.createLink(generationId)" in button
    assert "repeat_" in onboarding
    assert "<PrivateRepeatLinkUx />" in page
