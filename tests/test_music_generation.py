from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import random
from unittest.mock import AsyncMock

import pytest

from app.api.v1.generations import CreateGenerationRequest, generation_models, quote_generation
from app.core.config import settings
from app.db.models import AdminAccount, User, Wallet
from app.db.session import SessionFactory
from app.providers.kie import _extract_music_tracks
from app.services.music_generation import (
    MUSIC_MODEL_ID,
    MusicGenerationError,
    MusicGenerationService,
)
from app.services.music_media import MusicMediaIngestService
from app.services.wallet import WalletService

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
        "personaId",
        "personaModel",
        "duration",
    } <= fields
    assert model["required_fields"] == []


def test_simple_music_mode_is_bounded_and_drops_custom_only_fields() -> None:
    clean, cost = MusicGenerationService.prepare(
        {
            "prompt": "warm synth pop about a summer train",
            "customMode": False,
            "instrumental": False,
            "style": "should not reach simple-mode provider payload",
            "title": "ignored",
            "styleWeight": 0.9,
            "personaId": "persona_ignored",
            "personaModel": "style_persona",
            "duration": 120,
        }
    )
    assert clean == {
        "prompt": "warm synth pop about a summer train",
        "customMode": False,
        "instrumental": False,
    }
    assert cost > Decimal("0")

    with pytest.raises(MusicGenerationError, match="3000"):
        MusicGenerationService.prepare({"prompt": "x" * 3001, "customMode": False})


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
            "personaId": "persona_123",
            "personaModel": "style_persona",
            "duration": 212,
        }
    )
    assert clean["style"] == "cinematic synthwave, female vocal"
    assert clean["title"] == "Night Drive"
    assert clean["vocalGender"] == "f"
    assert clean["styleWeight"] == 0.65
    assert clean["personaId"] == "persona_123"
    assert clean["personaModel"] == "style_persona"
    assert clean["duration"] == 212

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
    with pytest.raises(MusicGenerationError, match="текст / промпт"):
        MusicGenerationService.prepare(
            {
                "customMode": True,
                "instrumental": False,
                "style": "pop",
                "title": "Song",
            }
        )
    with pytest.raises(MusicGenerationError, match="больше 0"):
        MusicGenerationService.prepare(
            {
                "customMode": True,
                "instrumental": True,
                "style": "ambient",
                "title": "Focus",
                "duration": 0,
            }
        )


def test_custom_instrumental_music_can_omit_prompt() -> None:
    clean, _cost = MusicGenerationService.prepare(
        {
            "customMode": True,
            "instrumental": True,
            "style": "minimal ambient piano",
            "title": "Focus Room",
            "duration": 180,
        }
    )
    assert "prompt" not in clean
    assert clean["style"] == "minimal ambient piano"
    assert clean["title"] == "Focus Room"
    assert clean["duration"] == 180


@pytest.mark.asyncio
async def test_active_admin_music_generation_is_free(monkeypatch: pytest.MonkeyPatch) -> None:
    async with SessionFactory() as session:
        user = User(
            telegram_id=random.randint(10_000_000_000_000, 10_999_999_999_999),
            first_name="Music admin",
        )
        session.add(user)
        await session.flush()
        monkeypatch.setattr(settings, "admin_bootstrap_telegram_ids", "")
        session.add(AdminAccount(user_id=user.id, role="admin", is_active=True))
        await WalletService.ensure_wallet(session, user.id)
        await session.commit()

        redis = AsyncMock()
        redis.eval.return_value = [1, 60]
        generation = await MusicGenerationService.create(
            session,
            redis,
            user_id=user.id,
            prompt="lo-fi instrumental",
            parameters={"instrumental": True, "customMode": False},
        )

        wallet = await session.get(Wallet, user.id)
        assert generation.cost_rox == Decimal("0.00")
        assert generation.parameters["_admin_free_generation"] is True
        assert Decimal(generation.parameters["_quoted_cost_rox"]) > Decimal("0")
        assert wallet is not None
        assert wallet.balance == Decimal("0.00")


@pytest.mark.asyncio
async def test_public_generation_catalog_and_quote_expose_music_in_rox() -> None:
    catalog = await generation_models(None, None)
    music = [item for item in catalog["models"] if item["id"] == MUSIC_MODEL_ID]
    assert len(music) == 1
    assert music[0]["media_type"] == "audio"

    quote = await quote_generation(
        CreateGenerationRequest(
            model_id=MUSIC_MODEL_ID,
            prompt="lo-fi instrumental for deep work",
            parameters={"instrumental": True, "customMode": False},
        ),
        None,
        None,  # public music quote is server-configured and does not need a DB read
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


def test_provider_worker_and_react_ui_have_explicit_music_branches() -> None:
    provider = (ROOT / "app/services/generation_provider.py").read_text(encoding="utf-8")
    worker = (ROOT / "app/workers/media.py").read_text(encoding="utf-8")
    ui = (ROOT / "frontend/mini-app/components/roxy-app.tsx").read_text(encoding="utf-8")
    router = (ROOT / "app/api/router.py").read_text(encoding="utf-8")

    assert 'provider_api == "suno_music"' in provider
    assert "create_music_task" in provider
    assert "get_music_task" in provider
    assert "MusicMediaAssetService.enqueue_results" in provider
    assert "MusicMediaIngestService.process_one" in worker
    assert 'audio: models.filter((m) => m.media_type === "audio").length' in ui
    assert "function modelIcon" in ui
    assert 'mediaType === "audio" ? "music" : "image"' in ui
    assert 'if (type === "audio") return <span className="media-placeholder audio"' in ui
    assert 'url && type === "audio" ? <audio src={url} controls/>' in ui
    assert "music_generations" not in router


def test_kie_provider_uses_dedicated_music_endpoints() -> None:
    source = (ROOT / "app/providers/kie.py").read_text(encoding="utf-8")
    assert 'post("/api/v1/generate"' in source
    assert '"/api/v1/generate/record-info"' in source
    assert '"SUCCESS"' in source
    assert '"GENERATE_AUDIO_FAILED"' in source
