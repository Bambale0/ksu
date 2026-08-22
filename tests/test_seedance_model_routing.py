from __future__ import annotations

import pytest

from app.services.generations import GenerationService
from app.services.model_routing import resolve_model_request


def test_seedance_25_reference_images_do_not_become_first_frame() -> None:
    routed = resolve_model_request(
        "seedance-2.5",
        {
            "prompt": "keep the subject consistent",
            "reference_image_urls": ["https://cdn.example/subject.png"],
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
        },
    )

    assert routed.parameters["reference_image_urls"] == ["https://cdn.example/subject.png"]
    assert "first_frame_url" not in routed.parameters


def test_seedance_20_reference_images_do_not_become_first_frame() -> None:
    routed = resolve_model_request(
        "seedance-2.0",
        {
            "prompt": "use subject and style references",
            "reference_image_urls": ["https://cdn.example/subject.png"],
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
    )

    assert routed.parameters["reference_image_urls"] == ["https://cdn.example/subject.png"]
    assert "first_frame_url" not in routed.parameters


def test_seedance_generic_input_url_becomes_first_frame_when_no_exact_media_fields() -> None:
    routed = resolve_model_request(
        "seedance-2.5",
        {
            "prompt": "animate this frame",
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
        input_url="https://cdn.example/source.png",
    )

    assert routed.parameters["first_frame_url"] == "https://cdn.example/source.png"
    assert "reference_image_urls" not in routed.parameters


def test_seedance_explicit_reference_mode_wins_over_generic_input_url() -> None:
    routed = resolve_model_request(
        "seedance-2.5",
        {
            "prompt": "reference mode",
            "reference_image_urls": ["https://cdn.example/ref.png"],
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "adaptive",
        },
        input_url="https://cdn.example/legacy-input.png",
    )

    assert routed.parameters["reference_image_urls"] == ["https://cdn.example/ref.png"]
    assert "first_frame_url" not in routed.parameters


@pytest.mark.asyncio
async def test_seedance_25_reference_mode_survives_generation_prepare() -> None:
    spec, clean, _cost, seconds, _unit = await GenerationService.prepare_request(
        object(),  # type: ignore[arg-type]
        model_id="seedance-2.5",
        prompt="consistent subject",
        parameters={
            "reference_image_urls": ["https://cdn.example/subject.png"],
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
    assert clean["reference_image_urls"] == ["https://cdn.example/subject.png"]
    assert "first_frame_url" not in clean
    assert seconds == 5


@pytest.mark.asyncio
async def test_seedance_20_explicit_hybrid_survives_generation_prepare() -> None:
    spec, clean, _cost, seconds, _unit = await GenerationService.prepare_request(
        object(),  # type: ignore[arg-type]
        model_id="seedance-2.0",
        prompt="hybrid control",
        parameters={
            "first_frame_url": "https://cdn.example/first.png",
            "last_frame_url": "https://cdn.example/last.png",
            "reference_image_urls": ["https://cdn.example/subject.png"],
            "reference_video_urls": ["https://cdn.example/motion.mp4"],
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "generate_audio": False,
            "web_search": False,
        },
    )

    assert spec.id == "seedance-2.0"
    assert clean["first_frame_url"].endswith("first.png")
    assert clean["last_frame_url"].endswith("last.png")
    assert clean["reference_image_urls"] == ["https://cdn.example/subject.png"]
    assert clean["reference_video_urls"] == ["https://cdn.example/motion.mp4"]
    assert seconds == 10