from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.api.v1.generations import CreateGenerationRequest, generation_models, quote_generation
from app.providers.kie import _extract_music_tracks
from app.services.music_generation import (
    MUSIC_MODEL_ID,
    MusicGenerationError,
    MusicGenerationService,
)
from app.services.music_media import MusicMediaIngestService

ROOT = Path(__file__).resolve().parents[1]


def test_music_model_is_first_class_audio_contract() -> None:
    model = MusicGenerationService.public_model()
    assert model["id"] == MUSIC_MODEL_ID
    assert model["family"] == "suno"
    assert model["operation"] == "text_to_music"
    assert model["media_type"] == "audio"
    assert model["price_mode"] == "flat"
    fields = {item["name"] for item in model["ui_schema"]["fields"]}
    assert {
        "prompt",
        "customMode",
        "instrumental",
        "style",
        "title",
        "negativeTags",
        "vocalGender",
        "styleWeight",
        "weirdnessConstraint",
        "audioWeight",
    } <= fields


def test_simple_music_mode_is_bounded_and_drops_custom_only_fields() -> None:
    clean, cost = MusicGenerationService.prepare(
        {
            "prompt": "warm synth pop about a summer train",
            "customMode": False,
            "instrumental": False,
            "style": "should not reach simple-mode provider payload",
            "title": "ignored",
            "styleWeight": 0.9,
        }
    )
    assert clean == {
        "prompt": "warm synth pop about a summer train",
        "customMode": False,
        "instrumental": False,
    }
    assert cost > Decimal("0")

    with pytest.raises(MusicGenerationError, match="500"):
        MusicGenerationService.prepare({"prompt": "x" * 501, "customMode": False})


def test_custom_music_mode_requires_terms_and_validates_advanced_weights() -> None:
    clean, _cost = MusicGenerationService.prepare(
        {
            "prompt": "[Verse]\nCity lights, quiet roads",
            "customMode": True,
            "instrumental": False,
            "style": "cinematic synthwave, female vocal",
            "title": "Night Drive",
            "vocalGender": "f",
            "styleWeight": 0.65,
            "weirdnessConstraint": 0.2,
            "audioWeight": 0.7,
        }
    )
    assert clean["style"] == "cinematic synthwave, female vocal"
    assert clean["title"] == "Night Drive"
    assert clean["vocalGender"] == "f"
    assert clean["styleWeight"] == 0.65

    with pytest.raises(MusicGenerationError, match="стиль"):
        MusicGenerationService.prepare(
            {"prompt": "lyrics", "customMode": True, "title": "Missing Style"}
        )
    with pytest.raises(MusicGenerationError, match="диапазоне 0..1"):
        MusicGenerationService.prepare(
            {
                "prompt": "lyrics",
                "customMode": True,
                "style": "pop",
                "title": "Song",
                "audioWeight": 2,
            }
        )


@pytest.mark.asyncio
async def test_public_generation_catalog_and_quote_expose_music_in_rox() -> None:
    catalog = await generation_models()
    music = [item for item in catalog["models"] if item["id"] == MUSIC_MODEL_ID]
    assert len(music) == 1
    assert music[0]["media_type"] == "audio"

    quote = await quote_generation(
        CreateGenerationRequest(
            model_id=MUSIC_MODEL_ID,
            prompt="lo-fi instrumental for deep work",
            parameters={"instrumental": True, "customMode": False},
        ),
        None,  # music quote is server-configured and does not need a DB read
    )
    assert quote["model_id"] == MUSIC_MODEL_ID
    assert quote["price_mode"] == "flat"
    assert Decimal(quote["cost_rox"]) > 0
    assert quote["cost_rox"] == quote["cost_rub"]


def test_kie_music_track_normalization_preserves_player_metadata() -> None:
    tracks = _extract_music_tracks(
        {
            "response": {
                "sunoData": [
                    {
                        "id": "track-1",
                        "audioUrl": "https://cdn.example.com/song.mp3",
                        "streamAudioUrl": "https://cdn.example.com/song-stream.mp3",
                        "imageUrl": "https://cdn.example.com/cover.jpg",
                        "modelName": "V5_5",
                        "title": "Night Drive",
                        "tags": "synthwave, cinematic",
                        "duration": 212.4,
                    }
                ]
            }
        }
    )
    assert tracks == [
        {
            "id": "track-1",
            "audio_url": "https://cdn.example.com/song.mp3",
            "stream_audio_url": "https://cdn.example.com/song-stream.mp3",
            "image_url": "https://cdn.example.com/cover.jpg",
            "prompt": "",
            "model_name": "V5_5",
            "title": "Night Drive",
            "tags": "synthwave, cinematic",
            "duration": 212.4,
            "create_time": "",
        }
    ]


def test_audio_ingest_accepts_audio_and_rejects_image_contract() -> None:
    assert MusicMediaIngestService._allowed_content_type("audio/mpeg", ".mp3") is True
    assert MusicMediaIngestService._allowed_content_type("audio/wav", ".wav") is True
    assert MusicMediaIngestService._allowed_content_type("image/png", ".png") is False
    assert MusicMediaIngestService._allowed_content_type("application/octet-stream", ".mp3") is True


def test_provider_worker_and_ui_have_explicit_music_branches() -> None:
    provider = (ROOT / "app/services/generation_provider.py").read_text(encoding="utf-8")
    worker = (ROOT / "app/workers/media.py").read_text(encoding="utf-8")
    ui = (ROOT / "app/web/mini_app/roxy-music.js").read_text(encoding="utf-8")
    brand = (ROOT / "app/web/mini_app/roxy-brand.js").read_text(encoding="utf-8")
    router = (ROOT / "app/api/router.py").read_text(encoding="utf-8")

    assert 'provider_api == "suno_music"' in provider
    assert "create_music_task" in provider
    assert "get_music_task" in provider
    assert "MusicMediaAssetService.enqueue_results" in provider
    assert "MusicMediaIngestService.process_one" in worker
    assert 'audio.className = "roxy-audio-player"' in ui
    assert 'data-roxy-media="audio"' in ui
    assert '/mini-app/roxy-music.js' in brand
    assert "music_generations" not in router


def test_kie_provider_uses_dedicated_music_endpoints() -> None:
    source = (ROOT / "app/providers/kie.py").read_text(encoding="utf-8")
    assert 'post("/api/v1/generate"' in source
    assert '"/api/v1/generate/record-info"' in source
    assert '"SUCCESS"' in source
    assert '"GENERATE_AUDIO_FAILED"' in source
