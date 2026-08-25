from __future__ import annotations

import pytest

from app.services.music_generation import MusicGenerationError, MusicGenerationService


def test_suno_rejects_string_boolean_mode_flags() -> None:
    with pytest.raises(MusicGenerationError, match="customMode"):
        MusicGenerationService.prepare({"customMode": "false", "prompt": "piano"})

    with pytest.raises(MusicGenerationError, match="instrumental"):
        MusicGenerationService.prepare(
            {
                "customMode": True,
                "instrumental": "false",
                "prompt": "lyrics",
                "style": "pop",
                "title": "Song",
            }
        )


def test_suno_simple_mode_prompt_limit_is_500() -> None:
    clean, _price = MusicGenerationService.prepare(
        {"customMode": False, "instrumental": False, "prompt": "a" * 500}
    )
    assert clean["prompt"] == "a" * 500
    assert clean["customMode"] is False
    assert clean["instrumental"] is False

    with pytest.raises(MusicGenerationError, match="500"):
        MusicGenerationService.prepare(
            {"customMode": False, "instrumental": False, "prompt": "a" * 501}
        )


def test_suno_custom_vocal_and_instrumental_requirements_remain_explicit() -> None:
    clean, _price = MusicGenerationService.prepare(
        {
            "customMode": True,
            "instrumental": False,
            "prompt": "a" * 5000,
            "style": "cinematic pop",
            "title": "Song",
        }
    )
    assert len(clean["prompt"]) == 5000

    with pytest.raises(MusicGenerationError, match="5000"):
        MusicGenerationService.prepare(
            {
                "customMode": True,
                "instrumental": False,
                "prompt": "a" * 5001,
                "style": "cinematic pop",
                "title": "Song",
            }
        )

    instrumental, _price = MusicGenerationService.prepare(
        {
            "customMode": True,
            "instrumental": True,
            "style": "ambient",
            "title": "No Vocals",
        }
    )
    assert "prompt" not in instrumental
    assert instrumental["instrumental"] is True


def test_suno_custom_style_title_and_weight_ranges_are_enforced() -> None:
    with pytest.raises(MusicGenerationError, match="стиль"):
        MusicGenerationService.prepare(
            {"customMode": True, "instrumental": True, "title": "Song"}
        )

    clean, _price = MusicGenerationService.prepare(
        {"customMode": True, "instrumental": True, "style": "pop"}
    )
    assert clean["style"] == "pop"
    assert "title" not in clean

    with pytest.raises(MusicGenerationError, match="1000"):
        MusicGenerationService.prepare(
            {
                "customMode": True,
                "instrumental": True,
                "style": "a" * 1001,
                "title": "Song",
            }
        )
    with pytest.raises(MusicGenerationError, match="80"):
        MusicGenerationService.prepare(
            {
                "customMode": True,
                "instrumental": True,
                "style": "pop",
                "title": "a" * 81,
            }
        )
    with pytest.raises(MusicGenerationError, match="0..1"):
        MusicGenerationService.prepare(
            {
                "customMode": True,
                "instrumental": True,
                "style": "pop",
                "title": "Song",
                "styleWeight": 1.1,
            }
        )
