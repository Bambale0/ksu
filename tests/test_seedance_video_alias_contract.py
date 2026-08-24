from __future__ import annotations

import pytest

from app.services.generations import GenerationService
from app.services.model_routing import resolve_model_request
from app.services.reference_resolver import ReferenceResolver


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


@pytest.mark.asyncio
async def test_seedance_25_video_upload_alias_survives_generation_prepare() -> None:
    spec, clean, _cost, seconds, _unit = await GenerationService.prepare_request(
        object(),  # type: ignore[arg-type]
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
