from __future__ import annotations

import pytest

from app.services.kie_video_contracts import (
    KieVideoContractError,
    normalize_kie_veo_input,
    normalize_kie_video_input,
)


def test_wan_t2v_uses_provider_ratio_field() -> None:
    payload = normalize_kie_video_input(
        "wan/2-7-text-to-video",
        {
            "prompt": "cinematic city",
            "resolution": "1080p",
            "aspect_ratio": "16:9",
            "duration": 5,
        },
    )

    assert payload["ratio"] == "16:9"
    assert "aspect_ratio" not in payload


def test_wan_i2v_modes_are_mutually_exclusive() -> None:
    first_last = normalize_kie_video_input(
        "wan/2-7-image-to-video",
        {
            "prompt": "move slowly",
            "first_frame_url": "https://example.com/first.png",
            "last_frame_url": "https://example.com/last.png",
            "duration": 5,
        },
    )
    assert first_last["last_frame_url"].endswith("last.png")

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "wan/2-7-image-to-video",
            {
                "prompt": "x",
                "first_frame_url": "https://example.com/first.png",
                "first_clip_url": "https://example.com/clip.mp4",
                "duration": 5,
            },
        )

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "wan/2-7-image-to-video",
            {
                "prompt": "x",
                "last_frame_url": "https://example.com/last.png",
                "duration": 5,
            },
        )


def test_wan_r2v_normalizes_legacy_single_reference_urls() -> None:
    payload = normalize_kie_video_input(
        "wan/2-7-r2v",
        {
            "prompt": "x",
            "reference_image": "https://example.com/ref.png",
            "reference_video": "https://example.com/ref.mp4",
            "duration": 5,
        },
    )

    assert payload["reference_image"] == ["https://example.com/ref.png"]
    assert payload["reference_video"] == ["https://example.com/ref.mp4"]


def test_wan_video_edit_accepts_documented_audio_setting() -> None:
    payload = normalize_kie_video_input(
        "wan/2-7-videoedit",
        {
            "prompt": "change outfit",
            "video_url": "https://example.com/source.mp4",
            "duration": 0,
            "audio_setting": {"mode": "auto"},
        },
    )

    assert payload["audio_setting"] == "auto"
    assert payload["duration"] == 0


def test_seedance_scenarios_and_reference_limits() -> None:
    payload = normalize_kie_video_input(
        "bytedance/seedance-1.5-pro",
        {
            "prompt": "x",
            "input_urls": ["https://example.com/a.png", "https://example.com/b.png"],
            "duration": 8,
        },
    )
    assert len(payload["input_urls"]) == 2

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "bytedance/seedance-1.5-pro",
            {
                "prompt": "x",
                "input_urls": [
                    "https://example.com/a.png",
                    "https://example.com/b.png",
                    "https://example.com/c.png",
                ],
                "duration": 8,
            },
        )

    with pytest.raises(KieVideoContractError, match="mutually exclusive"):
        normalize_kie_video_input(
            "bytedance/seedance-2",
            {
                "prompt": "x",
                "first_frame_url": "https://example.com/first.png",
                "last_frame_url": "https://example.com/last.png",
                "reference_image_urls": ["https://example.com/ref.png"],
                "reference_video_urls": ["https://example.com/ref.mp4"],
                "reference_audio_urls": ["https://example.com/ref.wav"],
                "duration": 10,
                "resolution": "720p",
                "aspect_ratio": "16:9",
            },
        )

    references = normalize_kie_video_input(
        "bytedance/seedance-2",
        {
            "prompt": "x",
            "reference_image_urls": ["https://example.com/ref.png"],
            "reference_video_urls": ["https://example.com/ref.mp4"],
            "reference_audio_urls": ["https://example.com/ref.wav"],
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
    )
    assert references["reference_video_urls"] == ["https://example.com/ref.mp4"]

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "bytedance/seedance-2",
            {
                "prompt": "x",
                "reference_image_urls": [f"https://example.com/{index}.png" for index in range(10)],
                "duration": 10,
                "resolution": "720p",
                "aspect_ratio": "16:9",
            },
        )

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "bytedance/seedance-2-5",
            {
                "prompt": "x",
                "first_frame_url": "https://example.com/first.png",
                "reference_video_urls": ["https://example.com/ref.mp4"],
                "duration": 10,
                "resolution": "720p",
                "aspect_ratio": "16:9",
            },
        )


def test_kling_3_validates_modes_multishot_and_elements() -> None:
    payload = normalize_kie_video_input(
        "kling-3.0/video",
        {
            "multi_shots": True,
            "image_urls": ["https://example.com/first.png"],
            "duration": 6,
            "aspect_ratio": "16:9",
            "mode": "4K",
            "multi_prompt": [
                {"prompt": "first scene", "duration": 3},
                {"prompt": "second scene", "duration": 3},
            ],
            "kling_elements": [
                {
                    "name": "hero",
                    "description": "main hero",
                    "element_input_urls": [
                        "https://example.com/hero-1.png",
                        "https://example.com/hero-2.png",
                    ],
                }
            ],
        },
    )

    assert payload["mode"] == "4K"
    assert len(payload["multi_prompt"]) == 2

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "kling-3.0/video",
            {
                "multi_shots": True,
                "image_urls": [
                    "https://example.com/first.png",
                    "https://example.com/last.png",
                ],
                "duration": 5,
                "mode": "pro",
                "multi_prompt": [{"prompt": "scene", "duration": 5}],
            },
        )

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "kling-3.0/video",
            {"duration": 5, "mode": "ultra", "aspect_ratio": "16:9"},
        )


def test_kling_motion_requires_exactly_one_image_and_video() -> None:
    payload = normalize_kie_video_input(
        "kling-3.0/motion-control",
        {
            "prompt": "dance",
            "input_urls": ["https://example.com/person.png"],
            "video_urls": ["https://example.com/motion.mp4"],
            "mode": "720p",
            "character_orientation": "image",
            "background_source": "input_video",
        },
    )
    assert payload["background_source"] == "input_video"

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "kling-2.6/motion-control",
            {
                "prompt": "dance",
                "input_urls": [],
                "video_urls": ["https://example.com/motion.mp4"],
                "mode": "720p",
            },
        )


def test_gemini_omni_enforces_weighted_upload_quota() -> None:
    payload = normalize_kie_video_input(
        "gemini-omni-video",
        {
            "prompt": "x",
            "image_urls": ["https://example.com/a.png", "https://example.com/b.png"],
            "video_list": [{"url": "https://example.com/ref.mp4", "start": 0, "ends": 5}],
            "character_ids": ["character-1", "character-2"],
            "audio_ids": ["audio-1"],
            "duration": 8,
        },
    )
    assert payload["video_list"][0]["url"].endswith("ref.mp4")

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input(
            "gemini-omni-video",
            {
                "prompt": "x",
                "image_urls": [f"https://example.com/{index}.png" for index in range(4)],
                "video_list": [{"url": "https://example.com/ref.mp4"}],
                "character_ids": ["a", "b"],
                "audio_ids": [],
                "duration": 8,
            },
        )


def test_grok_generation_and_task_operations_are_explicit() -> None:
    generated = normalize_kie_video_input(
        "grok-imagine/text-to-video",
        {"prompt": "x", "duration": 6, "resolution": "480p", "aspect_ratio": "2:3"},
    )
    assert generated["mode"] == "normal"

    extended = normalize_kie_video_input(
        "grok-imagine/extend",
        {"task_id": "task_123", "extend_at": 2, "extend_times": 6},
    )
    assert extended["extend_at"] == 2
    assert extended["extend_times"] == "6"

    with pytest.raises(KieVideoContractError):
        normalize_kie_video_input("grok-imagine/upscale", {"task_id": ""})


def test_veo_31_contract_enforces_generation_modes() -> None:
    payload = normalize_kie_veo_input(
        {
            "prompt": "x",
            "veo_model": "veo3_fast",
            "aspect_ratio": "9:16",
            "generation_type": "FIRST_AND_LAST_FRAMES_2_VIDEO",
            "image_urls": [
                "https://example.com/first.png",
                "https://example.com/last.png",
            ],
            "enable_fallback": False,
            "enable_translation": True,
        }
    )
    assert payload["generation_type"] == "FIRST_AND_LAST_FRAMES_2_VIDEO"

    with pytest.raises(KieVideoContractError):
        normalize_kie_veo_input(
            {
                "prompt": "x",
                "veo_model": "veo3",
                "generation_type": "REFERENCE_2_VIDEO",
                "image_urls": ["https://example.com/ref.png"],
            }
        )
