from __future__ import annotations

import pytest

from app.services.pinterest_flow_contract import (
    PinterestFlowError,
    build_pinterest_prompt,
    is_pinterest_trend,
    validate_pinterest_flow,
)


def test_pinterest_recipe_detection_uses_title_or_service_tag() -> None:
    assert is_pinterest_trend("Pinterest Editorial", {}) is True
    assert is_pinterest_trend("Editorial", {"tags": ["portrait", "pinterest-repeat"]}) is True
    assert is_pinterest_trend("Editorial", {"tags": ["portrait"]}) is False


def test_pinterest_flow_requires_scene_identity_and_consent() -> None:
    with pytest.raises(PinterestFlowError, match="2..7"):
        validate_pinterest_flow(
            reference_urls=["https://cdn.example/scene.jpg"],
            height_cm=175,
            weight_kg=70,
            confirmed=True,
        )

    with pytest.raises(PinterestFlowError, match="confirmation"):
        validate_pinterest_flow(
            reference_urls=["https://cdn.example/scene.jpg", "https://cdn.example/me.jpg"],
            height_cm=175,
            weight_kg=70,
            confirmed=False,
        )


def test_pinterest_flow_rejects_duplicate_identity_inputs_and_bad_measurements() -> None:
    duplicate = "https://cdn.example/same.jpg"
    with pytest.raises(PinterestFlowError, match="unique"):
        validate_pinterest_flow(
            reference_urls=[duplicate, duplicate],
            height_cm=175,
            weight_kg=70,
            confirmed=True,
        )

    with pytest.raises(PinterestFlowError, match="Height"):
        validate_pinterest_flow(
            reference_urls=["https://cdn.example/scene.jpg", "https://cdn.example/me.jpg"],
            height_cm=119,
            weight_kg=70,
            confirmed=True,
        )

    with pytest.raises(PinterestFlowError, match="Weight"):
        validate_pinterest_flow(
            reference_urls=["https://cdn.example/scene.jpg", "https://cdn.example/me.jpg"],
            height_cm=175,
            weight_kg=251,
            confirmed=True,
        )


def test_pinterest_prompt_keeps_scene_and_identity_roles_separate() -> None:
    prompt = build_pinterest_prompt(
        "curated hidden recipe",
        height_cm=175,
        weight_kg=70,
        reference_count=4,
    )
    assert "Image 1 is SCENE REFERENCE only" in prompt
    assert "Image 2 is PRIMARY IDENTITY REFERENCE" in prompt
    assert "Images 3..4 are SUPPORTING IDENTITY ANGLES (2 supplied)" in prompt
    assert "height 175 cm; weight 70 kg" in prompt
    assert prompt.endswith("curated hidden recipe")
