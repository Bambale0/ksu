from __future__ import annotations

import uuid
from decimal import Decimal

from app.api.v1.generations import _recreate_payload_for_generation
from app.db.models import Generation
from app.services.feed import FeedService
from app.services.generation_provider import GenerationProviderService
from app.services.reference_resolver import ReferenceResolver


def _generation(**overrides) -> Generation:  # type: ignore[no-untyped-def]
    data = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "kind": "text_to_image",
        "status": "succeeded",
        "prompt": "source prompt",
        "cost_rox": Decimal("1.00"),
        "provider": "kie",
        "parameters": {"_model_id": "nano-banana", "prompt": "source prompt"},
    }
    data.update(overrides)
    return Generation(**data)


def test_reference_resolver_exposes_roxy_owned_refs_for_feed_cards() -> None:
    generation = _generation(
        input_url="/uploads/refs/image/u/2026/08/input.png",
        parameters={
            "_model_id": "seedance-2.0",
            "reference_image_urls": [
                "/uploads/refs/image/u/2026/08/hero.png",
                "https://cdn.example/hero-fallback.png",
            ],
            "reference_video_urls": ["/uploads/refs/video/u/2026/08/motion.mp4"],
        },
    )

    context = ReferenceResolver.generation_context(generation)

    assert context.reference_images == [
        "/uploads/refs/image/u/2026/08/hero.png",
        "https://cdn.example/hero-fallback.png",
        "/uploads/refs/image/u/2026/08/input.png",
    ]
    assert context.reference_videos == ["/uploads/refs/video/u/2026/08/motion.mp4"]


def test_feed_runtime_patch_reference_key_aliases_remain_available() -> None:
    assert "reference_image_urls" in FeedService.REFERENCE_IMAGE_KEYS
    assert "reference_video_urls" in FeedService.REFERENCE_VIDEO_KEYS
    assert "input_video_url" in FeedService.REFERENCE_VIDEO_KEYS


def test_generation_provider_uses_generation_context_for_submit_payload() -> None:
    generation = _generation(
        input_url="/uploads/refs/image/u/2026/08/input.png",
        parameters={
            "_model_id": "nano-banana-edit",
            "resolution": "1K",
        },
    )

    payload = GenerationProviderService._input_for(generation)

    assert payload == {
        "resolution": "1K",
        "prompt": "source prompt",
        "image_url": "/uploads/refs/image/u/2026/08/input.png",
    }


def test_generation_provider_preserves_explicit_reference_payload() -> None:
    generation = _generation(
        input_url="/uploads/refs/image/u/2026/08/input.png",
        parameters={
            "_model_id": "seedance-2.0",
            "first_frame_url": "/uploads/refs/image/u/2026/08/first.png",
            "reference_video_urls": ["/uploads/refs/video/u/2026/08/motion.mp4"],
        },
    )

    payload = GenerationProviderService._input_for(generation)

    assert payload["first_frame_url"] == "/uploads/refs/image/u/2026/08/first.png"
    assert payload["reference_video_urls"] == ["/uploads/refs/video/u/2026/08/motion.mp4"]
    assert "image_url" not in payload


def test_history_recreate_preserves_reference_pipeline_without_private_fields() -> None:
    generation = _generation(
        input_url="/uploads/refs/image/u/2026/08/input.png",
        parameters={
            "_model_id": "gpt-image-2-i2i",
            "_provider_model": "private-provider-id",
            "_billing_seconds": None,
            "prompt": "source prompt",
            "input_urls": ["/uploads/refs/image/u/2026/08/input.png"],
            "resolution": "2K",
        },
    )

    payload = _recreate_payload_for_generation(generation)

    assert payload == {
        "model_id": "gpt-image-2-i2i",
        "prompt": "source prompt",
        "input_url": "/uploads/refs/image/u/2026/08/input.png",
        "billing_seconds": None,
        "parameters": {
            "input_urls": ["/uploads/refs/image/u/2026/08/input.png"],
            "resolution": "2K",
        },
    }
