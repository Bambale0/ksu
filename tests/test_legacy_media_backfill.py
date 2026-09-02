from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.media_legacy_backfill import LegacyMediaBackfillService

ROOT = Path(__file__).resolve().parents[1]


def generation_with(**parameters: object) -> SimpleNamespace:
    return SimpleNamespace(parameters=parameters)


def test_legacy_audio_detection_covers_suno_and_audio_snapshots() -> None:
    assert LegacyMediaBackfillService.is_audio_generation(
        generation_with(_provider_api="suno_music")
    )
    assert LegacyMediaBackfillService.is_audio_generation(
        generation_with(_media_type="audio")
    )
    assert LegacyMediaBackfillService.is_audio_generation(
        generation_with(_model_family="suno")
    )
    assert not LegacyMediaBackfillService.is_audio_generation(
        generation_with(_media_type="video", _model_family="kling")
    )


def test_legacy_backfill_routes_audio_to_music_ingest_and_other_media_to_generic_ingest() -> None:
    source = (ROOT / "app/services/media_legacy_backfill.py").read_text(encoding="utf-8")
    worker = (ROOT / "app/workers/media.py").read_text(encoding="utf-8")

    assert "MusicMediaAssetService.enqueue_results" in source
    assert "MediaAssetService.enqueue_results" in source
    assert "LegacyMediaBackfillService.ensure(session)" in worker
    assert "MediaAssetService.ensure_legacy(session)" not in worker
