from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_reference_backfill_does_not_iterate_expirable_orm_rows() -> None:
    source = _source("scripts/backfill_reference_static.py")

    assert "select(UserReference.id, UserReference.source_url)" in source
    assert "references = [(row_id, source_url)" in source
    assert "for reference_id, source_url in references:" in source
    assert "session.get(UserReference, reference_id)" in source
    assert "for row in rows:" not in source
    assert "rows = list((await session.scalars(stmt)).all())" not in source


def test_feed_backfill_does_not_iterate_expirable_orm_rows() -> None:
    source = _source("scripts/backfill_feed_static.py")

    assert "select(Generation.id)" in source
    assert "generation_ids = list((await session.scalars(stmt)).all())" in source
    assert "for generation_id in generation_ids:" in source
    assert "session.get(Generation, generation_id)" in source
    assert "for generation in generations:" not in source
