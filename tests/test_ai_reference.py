from __future__ import annotations

from pathlib import Path

import pytest

from app.api.v1.ai_reference import router
from app.services.ai_reference import AiReferenceError, AiReferenceService


def test_ai_reference_routes_are_registered() -> None:
    routes = {(route.path, frozenset(route.methods or set())) for route in router.routes}
    assert ("/ai-reference/quote", frozenset({"POST"})) in routes
    assert ("/ai-reference/run", frozenset({"POST"})) in routes


def test_create_reference_adult_uses_up_to_four_images_and_2k() -> None:
    recipe = AiReferenceService.build_request(
        scenario="create",
        subject="adult",
        reference_urls=["https://cdn.test/front.jpg", "https://cdn.test/profile.jpg"],
    )

    assert recipe.model_id == "nano-banana-pro"
    assert recipe.parameters == {
        "image_input": ["https://cdn.test/front.jpg", "https://cdn.test/profile.jpg"],
        "aspect_ratio": "3:4",
        "resolution": "2K",
        "output_format": "png",
    }
    assert "same adult person" in recipe.prompt
    assert "Do not beautify" in recipe.prompt


def test_create_reference_child_keeps_age_appropriate_identity_rules() -> None:
    recipe = AiReferenceService.build_request(
        scenario="create",
        subject="child",
        reference_urls=["https://cdn.test/child.jpg"],
    )

    assert recipe.parameters["resolution"] == "2K"
    assert "same child" in recipe.prompt
    assert "Do not add makeup" in recipe.prompt
    assert "adult features" in recipe.prompt


def test_create_reference_pet_preserves_animal_traits() -> None:
    recipe = AiReferenceService.build_request(
        scenario="create",
        subject="pet",
        reference_urls=["https://cdn.test/pet.jpg"],
    )

    assert recipe.parameters["aspect_ratio"] == "1:1"
    assert "same animal" in recipe.prompt
    assert "breed traits" in recipe.prompt
    assert "coat color and pattern" in recipe.prompt


def test_create_reference_requires_subject_and_limits_photo_count() -> None:
    with pytest.raises(AiReferenceError, match="Выберите"):
        AiReferenceService.build_request(
            scenario="create",
            subject=None,
            reference_urls=["https://cdn.test/person.jpg"],
        )

    with pytest.raises(AiReferenceError, match="от 1 до 4"):
        AiReferenceService.build_request(
            scenario="create",
            subject="adult",
            reference_urls=[f"https://cdn.test/{index}.jpg" for index in range(5)],
        )


def test_hd_reference_uses_single_image_4k_and_preserves_identity() -> None:
    recipe = AiReferenceService.build_request(
        scenario="hd",
        reference_urls=["https://cdn.test/reference.jpg"],
    )

    assert recipe.model_id == "nano-banana-pro"
    assert recipe.parameters == {
        "image_input": ["https://cdn.test/reference.jpg"],
        "aspect_ratio": "auto",
        "resolution": "4K",
        "output_format": "png",
    }
    assert "Enhance the technical image quality only" in recipe.prompt
    assert "Do not retouch the face" in recipe.prompt


def test_hd_reference_rejects_more_than_one_image() -> None:
    with pytest.raises(AiReferenceError, match="одна фотография"):
        AiReferenceService.build_request(
            scenario="hd",
            reference_urls=["https://cdn.test/a.jpg", "https://cdn.test/b.jpg"],
        )


def test_reference_editor_applies_user_change_but_preserves_identity() -> None:
    recipe = AiReferenceService.build_request(
        scenario="edit",
        reference_urls=["https://cdn.test/reference.jpg"],
        instruction="Добавь лёгкий макияж и сделай волосы холодным блондом",
    )

    assert recipe.model_id == "nano-banana-pro"
    assert recipe.parameters == {
        "image_input": ["https://cdn.test/reference.jpg"],
        "aspect_ratio": "auto",
        "resolution": "2K",
        "output_format": "png",
    }
    assert "Change only the requested attributes" in recipe.prompt
    assert "Добавь лёгкий макияж" in recipe.prompt


def test_reference_editor_requires_instruction() -> None:
    with pytest.raises(AiReferenceError, match="Опишите"):
        AiReferenceService.build_request(
            scenario="edit",
            reference_urls=["https://cdn.test/reference.jpg"],
            instruction="   ",
        )


def test_ai_reference_ui_exposes_all_three_working_scenarios() -> None:
    page = Path("frontend/mini-app/app/ai-reference/page.tsx").read_text(encoding="utf-8")
    client = Path("frontend/mini-app/lib/ai-reference-api.ts").read_text(encoding="utf-8")
    home_entry = Path("frontend/mini-app/components/ai-reference-home-entry.tsx").read_text(
        encoding="utf-8"
    )
    home = Path("frontend/mini-app/app/page.tsx").read_text(encoding="utf-8")

    assert "Создать референс" in page
    assert "Взрослый" in page
    assert "Детский" in page
    assert "Для животных" in page
    assert "Улучшить качество HD" in page
    assert "Редактор референса" in page
    assert "Что изменить?" in page
    assert "/api/v1/ai-reference/quote" in client
    assert "/api/v1/ai-reference/run" in client
    assert 'window.location.assign("/mini-app/ai-reference/")' in home_entry
    assert "AI РЕФЕРЕНС" in home_entry
    assert 'document.querySelector<HTMLElement>("#roxy-home-trend-folders")' in home_entry
    assert "host.prepend(mount)" in home_entry
    assert "<AiReferenceHomeEntry />" in home
    assert "<HomeTrendFolders />" in home
