from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.generations import GenerationService
from app.services.model_routing import resolve_model_request
from app.services.model_ui_contract import build_public_model_ui_schema
from app.services.reference_resolver import ReferenceResolver


class TrustedReferenceSession:
    async def scalar(self, _statement: Any) -> SimpleNamespace:
        return SimpleNamespace(
            duration_ms=5_000,
            probe_status="ready",
            size_bytes=1_000_000,
        )


def test_seedance_input_video_url_alias_becomes_reference_video() -> None:
    routed = resolve_model_request(
        "seedance-2.5",
        {
            "prompt": "follow uploaded motion",
            "input_video_url": "https://cdn.example/motion.mp4",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
        },
    )

    assert routed.parameters["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert "input_video_url" not in routed.parameters
    assert "first_frame_url" not in routed.parameters


def test_seedance_input_video_urls_alias_becomes_reference_videos() -> None:
    routed = resolve_model_request(
        "seedance-2.5",
        {
            "prompt": "use uploaded motion references",
            "input_video_urls": [
                "https://cdn.example/motion-a.mp4",
                "https://cdn.example/motion-b.mp4",
            ],
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
        },
    )

    assert routed.parameters["reference_video_urls"] == [
        "https://cdn.example/motion-a.mp4",
        "https://cdn.example/motion-b.mp4",
    ]
    assert "input_video_urls" not in routed.parameters
    assert "first_frame_url" not in routed.parameters


def test_seedance_input_image_urls_alias_becomes_reference_images() -> None:
    routed = resolve_model_request(
        "seedance-2.0",
        {
            "prompt": "use three image refs",
            "input_image_urls": [
                "https://cdn.example/ref-a.png",
                "https://cdn.example/ref-b.png",
                "https://cdn.example/ref-c.png",
            ],
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
        },
    )

    assert routed.parameters["reference_image_urls"] == [
        "https://cdn.example/ref-a.png",
        "https://cdn.example/ref-b.png",
        "https://cdn.example/ref-c.png",
    ]
    assert "input_image_urls" not in routed.parameters
    assert "first_frame_url" not in routed.parameters


@pytest.mark.asyncio
async def test_seedance_25_video_upload_alias_survives_generation_prepare() -> None:
    spec, clean, _cost, seconds, _unit = await GenerationService.prepare_request(
        TrustedReferenceSession(),
        model_id="seedance-2.5",
        prompt="motion from uploaded video",
        parameters={
            "input_video_url": "https://cdn.example/motion.mp4",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
            "output_format": "mp4",
            "generate_audio": False,
            "return_last_frame": False,
            "web_search": False,
            "nsfw_checker": True,
        },
    )

    assert spec.id == "seedance-2.5"
    assert clean["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert "input_video_url" not in clean
    assert "first_frame_url" not in clean
    assert seconds == 5


def test_reference_resolver_treats_video_alias_as_explicit_media_input() -> None:
    provider_input = ReferenceResolver.provider_input(
        prompt="use uploaded motion",
        input_url="https://cdn.example/fallback-frame.png",
        parameters={"input_video_url": "https://cdn.example/motion.mp4"},
    )

    assert provider_input["input_video_url"] == "https://cdn.example/motion.mp4"
    assert "image_url" not in provider_input


def test_seedance_video_alias_reaches_provider_input_as_canonical_reference() -> None:
    routed = resolve_model_request(
        "seedance-2.5",
        {
            "prompt": "send this to Kie",
            "input_video_url": "https://cdn.example/motion.mp4",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
        },
    )
    provider_input = ReferenceResolver.provider_input(
        prompt="send this to Kie",
        input_url=None,
        parameters=routed.parameters,
    )

    assert provider_input["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert "input_video_url" not in provider_input
    assert "image_url" not in provider_input


def test_generation_context_normalizes_saved_seedance_multirefs_before_provider_submit() -> None:
    generation = SimpleNamespace(
        prompt="send saved multirefs to Kie",
        input_url=None,
        parameters={
            "_model_id": "seedance-2.5",
            "_provider_model": "bytedance/seedance-2-5",
            "input_image_urls": [
                "https://cdn.example/ref-a.png",
                "https://cdn.example/ref-b.png",
                "https://cdn.example/ref-c.png",
            ],
            "input_video_urls": ["https://cdn.example/motion.mp4"],
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
        },
    )

    context = ReferenceResolver.generation_context(generation)

    assert context.provider_input["reference_image_urls"] == [
        "https://cdn.example/ref-a.png",
        "https://cdn.example/ref-b.png",
        "https://cdn.example/ref-c.png",
    ]
    assert context.provider_input["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert "input_image_urls" not in context.provider_input
    assert "input_video_urls" not in context.provider_input
    assert context.parameters["_provider_model"] == "bytedance/seedance-2-5"


def test_seedance_reference_mode_ui_appends_images_instead_of_replacing() -> None:
    schema = build_public_model_ui_schema(
        {
            "id": "seedance-2.0",
            "known_fields": [
                "prompt",
                "reference_image_urls",
                "reference_video_urls",
                "reference_audio_urls",
                "duration",
                "resolution",
                "aspect_ratio",
            ],
            "required_fields": ["prompt", "duration"],
            "media_type": "video",
            "operation": "multimodal_video",
        }
    )

    fields = {field["name"]: field for field in schema["fields"]}
    assert fields["reference_image_urls"]["control"] == "files"
    assert fields["reference_image_urls"]["max_items"] >= 3

    scenarios = {item["id"]: item for item in schema["scenario"]["items"]}
    assert scenarios["references"]["title"] == "Мультиреференсы"
    assert scenarios["references"]["visible_fields"] == [
        "reference_image_urls",
        "reference_video_urls",
        "reference_audio_urls",
    ]
