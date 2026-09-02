from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.services.media_legacy_backfill import LegacyMediaBackfillService

ROOT = Path(__file__).resolve().parents[1]


def generation_with(*, kind: str = "image", **parameters: object) -> SimpleNamespace:
    return SimpleNamespace(kind=kind, parameters=parameters)


def job_with(status: str, error: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(status=status, last_error=error)


def test_legacy_audio_detection_covers_suno_and_audio_snapshots() -> None:
    assert LegacyMediaBackfillService.is_audio_generation(generation_with(kind="music"))
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


def test_only_misrouted_generic_audio_jobs_are_reset() -> None:
    assert LegacyMediaBackfillService.is_misrouted_generic_audio_job(job_with("pending"))
    assert LegacyMediaBackfillService.is_misrouted_generic_audio_job(
        job_with("failed", "Unsupported media content type: audio/mpeg")
    )
    assert not LegacyMediaBackfillService.is_misrouted_generic_audio_job(
        job_with("audio_pending", "temporary upstream failure")
    )
    assert not LegacyMediaBackfillService.is_misrouted_generic_audio_job(
        job_with("failed", "Unsupported audio content type: application/pdf")
    )


def test_legacy_backfill_routes_and_repairs_audio_storage_jobs() -> None:
    source = (ROOT / "app/services/media_legacy_backfill.py").read_text(encoding="utf-8")
    worker = (ROOT / "app/workers/media.py").read_text(encoding="utf-8")

    assert "MusicMediaAssetService.enqueue_results" in source
    assert "MediaAssetService.enqueue_results" in source
    assert 'Generation.kind == "music"' in source
    assert 'job.status = "audio_pending"' in source
    assert 'asset.status = "audio_pending"' in source
    assert "job.attempts = 0" in source
    assert "LegacyMediaBackfillService.ensure(session)" in worker
    assert "MediaAssetService.ensure_legacy(session)" not in worker
