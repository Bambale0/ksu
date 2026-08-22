from __future__ import annotations

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
