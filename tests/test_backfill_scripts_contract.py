from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_BACKFILL = ROOT / "scripts" / "backfill_reference_static.py"
FEED_BACKFILL = ROOT / "scripts" / "backfill_feed_static.py"


def test_reference_backfill_rehydrates_rows_after_commit_or_rollback() -> None:
    source = REFERENCE_BACKFILL.read_text(encoding="utf-8")

    assert "select(UserReference.id, UserReference.source_url)" in source
    assert "references = [(row_id, source_url)" in source
    assert "for reference_id, source_url in references:" in source
    assert "session.get(UserReference, reference_id)" in source
    assert "reference={reference_id}" in source
    assert "reference={row.id}" not in source
    assert "reference_id = row.id" not in source
    assert "source_url = row.source_url" not in source
    assert "for row in rows:" not in source


def test_feed_backfill_rehydrates_rows_after_commit_or_rollback() -> None:
    source = FEED_BACKFILL.read_text(encoding="utf-8")

    assert "select(Generation.id)" in source
    assert "generation_ids = list((await session.scalars(stmt)).all())" in source
    assert "for generation_id in generation_ids:" in source
    assert "session.get(Generation, generation_id)" in source
    assert "generation={generation_id}" in source
    assert "generation={generation.id}" not in source
    assert "generation_id = generation.id" not in source
    assert "for generation in generations:" not in source
