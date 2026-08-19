from __future__ import annotations

import pytest

from app.services.kie_image_contracts import (
    KieImageContractError,
    normalize_kie_image_input,
)


def test_seedream_4_count_is_validated_and_added_to_provider_prompt() -> None:
    payload = normalize_kie_image_input(
        "bytedance/seedream-v4-text-to-image",
        {
            "prompt": "Editorial portrait in a studio",
            "image_size": "portrait_4_3",
            "image_resolution": "2K",
            "max_images": 4,
        },
    )

    assert payload["max_images"] == 4
    assert payload["prompt"].startswith("Editorial portrait in a studio")
    assert "Generate exactly 4 images in this set." in payload["prompt"]

    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "bytedance/seedream-v4-text-to-image",
            {"prompt": "x", "max_images": 7},
        )


def test_gpt_image_2_rejects_large_resolution_ratio_combinations() -> None:
    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "gpt-image-2-text-to-image",
            {"prompt": "x", "resolution": "4K", "aspect_ratio": "5:4"},
        )

    payload = normalize_kie_image_input(
        "gpt-image-2-text-to-image",
        {"prompt": "x", "resolution": "2K", "aspect_ratio": "16:9"},
    )
    assert payload["resolution"] == "2K"
    assert payload["aspect_ratio"] == "16:9"


def test_wan_standard_and_pro_apply_documented_image_limits() -> None:
    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "wan/2-7-image",
            {"prompt": "x", "resolution": "4K", "n": 1},
        )

    payload = normalize_kie_image_input(
        "wan/2-7-image-pro",
        {
            "prompt": "x",
            "input_urls": ["https://example.com/reference.png"],
            "resolution": "4K",
            "n": 1,
            "thinking_mode": True,
        },
    )
    assert payload["resolution"] == "2K"
    assert payload["thinking_mode"] is False

    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "wan/2-7-image-pro",
            {"prompt": "x", "input_urls": [f"https://e/{i}.png" for i in range(10)]},
        )

    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "wan/2-7-image",
            {"prompt": "x", "n": 5, "enable_sequential": False},
        )

    gallery = normalize_kie_image_input(
        "wan/2-7-image",
        {"prompt": "x", "n": 12, "enable_sequential": True, "thinking_mode": True},
    )
    assert gallery["n"] == 12
    assert gallery["thinking_mode"] is False


def test_nano_banana_2_limits_references_and_enums() -> None:
    payload = normalize_kie_image_input(
        "nano-banana-2",
        {
            "prompt": "x",
            "image_input": [f"https://e/{i}.png" for i in range(14)],
            "aspect_ratio": "1:8",
            "resolution": "4K",
            "output_format": "png",
        },
    )
    assert len(payload["image_input"]) == 14

    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "nano-banana-2",
            {"prompt": "x", "image_input": [f"https://e/{i}.png" for i in range(15)]},
        )

    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "nano-banana-2",
            {"prompt": "x", "aspect_ratio": "7:5"},
        )


def test_grok_image_contracts_are_explicit() -> None:
    payload = normalize_kie_image_input(
        "grok-imagine/text-to-image",
        {"prompt": "x", "aspect_ratio": "9:16", "enable_pro": True},
    )
    assert payload["enable_pro"] is True

    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "grok-imagine/text-to-image",
            {"prompt": "x", "enable_pro": "true"},
        )

    with pytest.raises(KieImageContractError):
        normalize_kie_image_input(
            "grok-imagine/image-to-image",
            {"prompt": "x", "image_urls": ["https://e/1.png", "https://e/2.png"]},
        )


def test_unknown_model_is_not_mutated() -> None:
    original = {"prompt": "x", "resolution": "anything"}
    result = normalize_kie_image_input("some-future-video-model", original)
    assert result == original
    assert result is not original
