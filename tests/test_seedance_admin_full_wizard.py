from __future__ import annotations

import pytest

from app.bot.handlers.seedance_test import _mode_keyboard
from app.services.seedance_test_wizard import (
    SeedanceWizardError,
    build_seedance_payload,
    get_seedance_test_spec,
)


def _callbacks(markup) -> list[str]:
    return [
        str(button.callback_data or "")
        for row in markup.inline_keyboard
        for button in row
    ]


def test_seedance_mode_keyboard_exposes_full_model_specific_modes() -> None:
    callbacks_20 = _callbacks(_mode_keyboard("seedance-2.0"))
    assert "seedance-test:mode:text" in callbacks_20
    assert "seedance-test:mode:reference" in callbacks_20
    assert "seedance-test:mode:frame" in callbacks_20
    assert "seedance-test:mode:edit" not in callbacks_20

    callbacks_25 = _callbacks(_mode_keyboard("seedance-2.5"))
    assert "seedance-test:mode:text" in callbacks_25
    assert "seedance-test:mode:reference" in callbacks_25
    assert "seedance-test:mode:frame" in callbacks_25
    assert "seedance-test:mode:edit" in callbacks_25


def test_seedance_wizard_specs_match_provider_limits() -> None:
    spec20 = get_seedance_test_spec("seedance-2.0")
    assert (spec20.min_duration, spec20.max_duration) == (4, 15)
    assert spec20.resolutions == ("480p", "720p", "1080p", "4k")
    assert (spec20.max_image_refs, spec20.max_video_refs, spec20.max_audio_refs) == (9, 3, 3)
    assert spec20.max_total_refs == 12
    assert spec20.supports_edit is False

    spec25 = get_seedance_test_spec("seedance-2.5")
    assert (spec25.min_duration, spec25.max_duration) == (4, 30)
    assert spec25.resolutions == ("480p", "720p", "1080p")
    assert (spec25.max_image_refs, spec25.max_video_refs, spec25.max_audio_refs) == (30, 10, 10)
    assert spec25.max_total_refs == 50
    assert spec25.supports_edit is True


def test_seedance_20_reference_payload_uses_canonical_provider_fields() -> None:
    payload = build_seedance_payload(
        {
            "model_name": "seedance-2.0",
            "mode": "reference",
            "prompt": "cinematic motion",
            "resolution": "1080p",
            "duration": 12,
            "aspect_ratio": "9:16",
            "reference_images": ["https://media.example/a.jpg", "https://media.example/b.jpg"],
            "reference_videos": ["https://media.example/motion.mp4"],
            "reference_audios": ["https://media.example/music.mp3"],
        }
    )

    assert payload == {
        "resolution": "1080p",
        "duration": 12,
        "aspect_ratio": "9:16",
        "generate_audio": True,
        "reference_images": [
            {"url": "https://media.example/a.jpg"},
            {"url": "https://media.example/b.jpg"},
        ],
        "reference_videos": [{"url": "https://media.example/motion.mp4"}],
        "reference_audios": [{"url": "https://media.example/music.mp3"}],
    }


def test_seedance_25_edit_follows_source_duration_and_aspect() -> None:
    payload = build_seedance_payload(
        {
            "model_name": "seedance-2.5",
            "mode": "edit",
            "prompt": "replace the character, preserve motion",
            "resolution": "720p",
            "reference_images": ["https://media.example/hero.jpg"],
            "reference_videos": ["https://media.example/source.mp4"],
            "reference_audios": [],
        }
    )

    assert payload["resolution"] == "720p"
    assert payload["omni_reference_task_type"] == "edit"
    assert payload["reference_videos"] == [{"url": "https://media.example/source.mp4"}]
    assert "duration" not in payload
    assert "aspect_ratio" not in payload


def test_seedance_25_frame_payload_is_adaptive_and_separate_from_refs() -> None:
    payload = build_seedance_payload(
        {
            "model_name": "seedance-2.5",
            "mode": "frame",
            "prompt": "camera pushes in",
            "resolution": "1080p",
            "duration": 8,
            "aspect_ratio": "adaptive",
            "start_image": "https://media.example/start.jpg",
            "end_image": "https://media.example/end.jpg",
            "reference_images": [],
            "reference_videos": [],
            "reference_audios": [],
        }
    )

    assert payload["start_image"] == {"url": "https://media.example/start.jpg"}
    assert payload["end_image"] == {"url": "https://media.example/end.jpg"}
    assert payload["aspect_ratio"] == "adaptive"
    assert "reference_images" not in payload


def test_seedance_reference_limits_fail_before_provider_spend() -> None:
    with pytest.raises(SeedanceWizardError, match="12"):
        build_seedance_payload(
            {
                "model_name": "seedance-2.0",
                "mode": "reference",
                "prompt": "x",
                "resolution": "720p",
                "duration": 8,
                "aspect_ratio": "16:9",
                "reference_images": [f"https://media.example/{i}.jpg" for i in range(9)],
                "reference_videos": [f"https://media.example/{i}.mp4" for i in range(3)],
                "reference_audios": ["https://media.example/a.mp3"],
            }
        )


def test_seedance_20_audio_reference_requires_visual_reference() -> None:
    with pytest.raises(SeedanceWizardError, match="фото или видео"):
        build_seedance_payload(
            {
                "model_name": "seedance-2.0",
                "mode": "reference",
                "prompt": "x",
                "resolution": "720p",
                "duration": 8,
                "aspect_ratio": "16:9",
                "reference_images": [],
                "reference_videos": [],
                "reference_audios": ["https://media.example/a.mp3"],
            }
        )


def test_seedance_25_edit_requires_video_reference() -> None:
    with pytest.raises(SeedanceWizardError, match="видео"):
        build_seedance_payload(
            {
                "model_name": "seedance-2.5",
                "mode": "edit",
                "prompt": "x",
                "resolution": "720p",
                "reference_images": ["https://media.example/a.jpg"],
                "reference_videos": [],
                "reference_audios": [],
            }
        )


def test_seedance_prompt_aspect_overrides_wizard_selection() -> None:
    payload = build_seedance_payload(
        {
            "model_name": "seedance-2.5",
            "mode": "reference",
            "prompt": (
                "SEEDANCE 2.5 | 10 SEC | 9:16 | ULTRA PHOTOREALISTIC\n"
                "Создай видео ровно 10 секунд, формат 9:16. @Image1 — лицо."
            ),
            "resolution": "720p",
            "duration": 10,
            "aspect_ratio": "3:4",
            "reference_images": ["https://media.example/a.jpg"],
            "reference_videos": [],
            "reference_audios": [],
        }
    )

    assert payload["aspect_ratio"] == "9:16"


def test_seedance_prompt_with_multiple_ratios_does_not_guess_intent() -> None:
    payload = build_seedance_payload(
        {
            "model_name": "seedance-2.5",
            "mode": "reference",
            "prompt": "Take a 16:9 composition and adapt it to 9:16 using @Image1.",
            "resolution": "720p",
            "duration": 10,
            "aspect_ratio": "9:16",
            "reference_images": ["https://media.example/a.jpg"],
            "reference_videos": [],
            "reference_audios": [],
        }
    )
    assert payload["aspect_ratio"] == "9:16"
