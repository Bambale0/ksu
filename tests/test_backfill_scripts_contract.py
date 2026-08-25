from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_BACKFILL = ROOT / "scripts" / "backfill_reference_static.py"
FEED_BACKFILL = ROOT / "scripts" / "backfill_feed_static.py"


def test_reference_backfill_does_not_touch_expired_orm_rows_after_rollback() -> None:
    source = REFERENCE_BACKFILL.read_text(encoding="utf-8")

    assert "reference_id = row.id" in source
    assert "source_url = row.source_url" in source
    assert "reference={reference_id}" in source
    assert "reference={row.id}" not in source


def test_feed_backfill_does_not_touch_expired_orm_rows_after_rollback() -> None:
    source = FEED_BACKFILL.read_text(encoding="utf-8")

    assert "generation_id = generation.id" in source
    assert "generation={generation_id}" in source
    assert "generation={generation.id}" not in source
