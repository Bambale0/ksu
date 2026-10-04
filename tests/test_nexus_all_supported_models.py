from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.providers.nexus import NexusClient, _extract_result_urls
from app.services.nexus_generation_provider import (
    NEXUS_MODEL_MAP,
    NexusGenerationProviderService,
    NexusGenerationUnsupportedInput,
)


EXPECTED_NEXUS_MODEL_IDS = {
    "nano-banana",
    "nano-banana-edit",
    "nano-banana-pro",
    "nano-banana-2",
    "nano-banana-2-lite",
    "gpt-image-2-t2i",
    "gpt-image-2-i2i",
    "seedream-5-lite-t2i",
    "seedream-5-lite-i2i",
    "seedream-5-pro-t2i",
    "seedream-5-pro-i2i",
    "seedance-2.0",
    "seedance-2.0-fast",
    "seedance-2.0-mini",
    "seedance-2.5",
    "wan-2.7-t2v",
    "wan-2.7-i2v",
    "kling-3.0",
    "kling-motion-2.6",
    "veo-3.1",
    "gemini-omni-video",
}


def test_nexus_model_map_covers_all_compatible_bot_models_and_never_grok() -> None:
    assert set(NEXUS_MODEL_MAP) == EXPECTED_NEXUS_MODEL_IDS
    assert NexusGenerationProviderService.MODEL_IDS == frozenset(EXPECTED_NEXUS_MODEL_IDS)
    assert not any(model.startswith("grok-") for model in NEXUS_MODEL_MAP)


def test_nexus_normalizes_seedance_multimodal_references() -> None:
    normalized = NexusGenerationProviderService._normalize_input(
        "seedance-2.5",
        {
            "prompt": "shot",
            "reference_image_urls": ["https://example.test/a.jpg"],
            "reference_video_urls": ["https://example.test/a.mp4"],
            "reference_audio_urls": ["https://example.test/a.wav"],
            "aspect_ratio": "adaptive",
            "duration": 8,
            "resolution": "720p",
            "generate_audio": True,
        },
    )
    assert normalized == {
        "model_name": "seedance-2.5",
        "prompt": "shot",
        "image_urls": ["https://example.test/a.jpg"],
        "video_urls": ["https://example.test/a.mp4"],
        "audio_urls": ["https://example.test/a.wav"],
        "aspect_ratio": "adaptive",
        "duration": 8,
        "resolution": "720p",
        "generate_audio": True,
    }


def test_nexus_normalizes_veo_31_variant_without_changing_semantics() -> None:
    normalized = NexusGenerationProviderService._normalize_input(
        "veo-3.1",
        {
            "prompt": "cinematic",
            "veo_model": "veo3_fast",
            "image_urls": ["https://example.test/start.jpg"],
            "aspect_ratio": "16:9",
            "_billing_seconds": 8,
            "resolution": "1080p",
        },
    )
    assert normalized["model_name"] == "veo-3.1-fast"
    assert normalized["image_url"] == "https://example.test/start.jpg"
    assert normalized["duration"] == 8
    assert normalized["resolution"] == "1080p"


def test_nexus_kling_3_rejects_richer_kie_only_mode_before_submission() -> None:
    with pytest.raises(NexusGenerationUnsupportedInput, match="Kling 3"):
        NexusGenerationProviderService._normalize_input(
            "kling-3.0",
            {
                "prompt": "multi shot",
                "duration": 5,
                "multi_shots": True,
                "multi_prompt": [{"prompt": "a"}],
            },
        )


@pytest.mark.asyncio
async def test_nexus_generic_generate_posts_exact_params() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        assert request.headers["Idempotency-Key"] == "generation:abc"
        return httpx.Response(202, json={"task_id": "task-1"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusClient("test-key", client=http_client)
        task_id = await client.create_generation(
            params={"model_name": "seedance-2.0", "prompt": "go", "duration": 5},
            idempotency_key="generation:abc",
        )

    assert task_id == "task-1"
    assert captured == {
        "params": {"model_name": "seedance-2.0", "prompt": "go", "duration": 5}
    }


def test_nexus_task_result_extraction_supports_video_and_image_shapes() -> None:
    assert _extract_result_urls({"image_urls": ["https://x/a.png"]}) == ["https://x/a.png"]
    assert _extract_result_urls({"video_url": "https://x/a.mp4"}) == ["https://x/a.mp4"]
    assert _extract_result_urls({"video_urls": ["https://x/a.mp4", "https://x/b.mp4"]}) == [
        "https://x/a.mp4",
        "https://x/b.mp4",
    ]


@pytest.mark.asyncio
async def test_unsupported_nexus_shape_falls_back_before_remote_task_is_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    generation = SimpleNamespace(
        provider="nexus",
        status="submitting",
        external_id=None,
        parameters={},
    )

    class StubSession:
        async def scalar(self, _statement):
            return generation

    fallback = AsyncMock(return_value=SimpleNamespace(provider="kie"))
    refund = AsyncMock()
    monkeypatch.setattr(
        "app.services.nexus_generation_provider.switch_to_fallback",
        fallback,
    )
    monkeypatch.setattr(
        "app.services.nexus_generation_provider.GenerationProviderService.fail_and_refund",
        refund,
    )

    await NexusGenerationProviderService._record_submission_error(
        StubSession(),  # type: ignore[arg-type]
        uuid.uuid4(),
        NexusGenerationUnsupportedInput("Kling 3 multi-shot"),
    )

    fallback.assert_awaited_once()
    refund.assert_not_awaited()


def test_nexus_motion_uses_trusted_billing_duration() -> None:
    normalized = NexusGenerationProviderService._normalize_input(
        "kling-motion-2.6",
        {
            "prompt": "follow motion",
            "input_urls": ["https://example.test/person.jpg"],
            "video_urls": ["https://example.test/motion.mp4"],
            "mode": "1080p",
            "character_orientation": "image",
            "_billing_seconds": 12,
        },
    )
    assert normalized["model_name"] == "kling-v2.6-motion-1080p"
    assert normalized["duration"] == 12


@pytest.mark.parametrize(
    ("model_id", "payload", "message"),
    [
        (
            "kling-3.0",
            {"prompt": "shot", "duration": 5, "mode": "4K"},
            "4K",
        ),
        (
            "kling-3.0",
            {"prompt": "", "duration": 5},
            "requires a prompt",
        ),
        (
            "veo-3.1",
            {
                "prompt": "shot",
                "veo_model": "veo3_fast",
                "watermark_text": "brand",
                "_billing_seconds": 8,
            },
            "watermark",
        ),
        (
            "seedream-5-lite-t2i",
            {"prompt": "image", "quality": "unknown"},
            "quality",
        ),
    ],
)
def test_nexus_materially_incompatible_options_fall_back(
    model_id: str, payload: dict[str, object], message: str
) -> None:
    with pytest.raises(NexusGenerationUnsupportedInput, match=message):
        NexusGenerationProviderService._normalize_input(model_id, payload)


def test_nexus_wan_t2v_maps_kie_ratio_to_nexus_aspect_ratio() -> None:
    normalized = NexusGenerationProviderService._normalize_input(
        "wan-2.7-t2v",
        {
            "prompt": "flight",
            "duration": 5,
            "ratio": "9:16",
            "resolution": "1080p",
        },
    )
    assert normalized["model_name"] == "wan/2-7-text-to-video"
    assert normalized["aspect_ratio"] == "9:16"


@pytest.mark.parametrize(
    ("model_id", "payload", "message"),
    [
        (
            "nano-banana",
            {"prompt": "image", "output_format": "jpeg", "aspect_ratio": "1:1"},
            "output format",
        ),
        (
            "gpt-image-2-t2i",
            {"prompt": "image", "resolution": "1K", "aspect_ratio": "1:1"},
            "resolution",
        ),
        (
            "seedream-5-lite-t2i",
            {"prompt": "image", "aspect_ratio": "1:1", "quality": "basic"},
            "aspect ratio",
        ),
        (
            "seedream-5-lite-t2i",
            {"prompt": "image", "quality": "ultra"},
            "Ultra",
        ),
        (
            "seedream-5-pro-t2i",
            {"prompt": "image", "aspect_ratio": "21:9", "quality": "basic"},
            "21:9",
        ),
        (
            "wan-2.7-i2v",
            {
                "prompt": "move",
                "duration": 5,
                "aspect_ratio": "16:9",
                "first_frame_url": "https://example.test/a.jpg",
            },
            "aspect ratio",
        ),
        (
            "seedance-2.0",
            {"prompt": "video", "duration": 5, "web_search": True},
            "web search",
        ),
        (
            "seedance-2.5",
            {"prompt": "video", "duration": 5, "output_format": "mov"},
            "MOV",
        ),
    ],
)
def test_nexus_does_not_silently_drop_user_selected_semantics(
    model_id: str, payload: dict[str, object], message: str
) -> None:
    with pytest.raises(NexusGenerationUnsupportedInput, match=message):
        NexusGenerationProviderService._normalize_input(model_id, payload)


def test_seedream_quality_maps_to_documented_nexus_resolution() -> None:
    lite_basic = NexusGenerationProviderService._normalize_input(
        "seedream-5-lite-t2i", {"prompt": "image", "quality": "basic"}
    )
    lite_high = NexusGenerationProviderService._normalize_input(
        "seedream-5-lite-t2i", {"prompt": "image", "quality": "high"}
    )
    pro_basic = NexusGenerationProviderService._normalize_input(
        "seedream-5-pro-t2i",
        {"prompt": "image", "quality": "basic", "aspect_ratio": "1:1"},
    )
    pro_high = NexusGenerationProviderService._normalize_input(
        "seedream-5-pro-t2i",
        {"prompt": "image", "quality": "high", "aspect_ratio": "16:9"},
    )
    assert lite_basic["resolution"] == "2K"
    assert lite_high["resolution"] == "3K"
    assert pro_basic["resolution"] == "1K"
    assert pro_high["resolution"] == "2K"
