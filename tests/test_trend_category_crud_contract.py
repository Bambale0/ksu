from __future__ import annotations

from pathlib import Path
import uuid

import pytest

from app.services.trend_collections import TrendCollectionError, TrendCollectionService


def test_category_hashtags_normalize_hash_prefix_and_case() -> None:
    collection = TrendCollectionService.normalize_collection(
        {
            "title": "Праздник",
            "description": "",
            "aliases": ["#ДР", "др", "##Birthday", "праздник-дома"],
        },
        collection_id="party",
    )

    assert collection["aliases"] == ["др", "birthday", "праздник-дома"]


def test_initialized_state_does_not_resurrect_deleted_default_category() -> None:
    state = TrendCollectionService.merge_state(
        {
            "schema_version": 2,
            "initialized": True,
            "collections": [],
            "assignments": {"trend-1": "birthday"},
            "auto_assignments": ["trend-1"],
        }
    )

    assert [item["id"] for item in state["collections"]] == ["trends"]
    assert state["assignments"] == {}
    assert state["auto_assignments"] == []


def test_v1_state_is_migrated_with_existing_defaults_before_first_write() -> None:
    state = TrendCollectionService.merge_state({"schema_version": 1, "collections": []})

    assert [item["id"] for item in state["collections"]] == ["trends", "birthday"]
    assert state["schema_version"] == 2
    assert state["initialized"] is True


def test_duplicate_category_hashtag_is_rejected_even_when_other_category_is_hidden() -> None:
    with pytest.raises(TrendCollectionError, match="#birthday"):
        TrendCollectionService._validate_unique_hashtags(
            [
                TrendCollectionService.normalize_collection(
                    {"title": "День рождения", "aliases": ["birthday"], "is_active": False},
                    collection_id="birthday",
                ),
                TrendCollectionService.normalize_collection(
                    {"title": "Party", "aliases": ["#Birthday"], "is_active": True},
                    collection_id="party",
                ),
            ]
        )


@pytest.mark.asyncio
async def test_live_trends_root_cannot_be_deleted() -> None:
    with pytest.raises(TrendCollectionError, match="нельзя удалить"):
        await TrendCollectionService.delete_collection(  # type: ignore[arg-type]
            None,
            admin_id=uuid.uuid4(),
            collection_id="trends",
        )


def test_admin_api_and_ui_expose_real_category_delete_and_hashtags() -> None:
    root = Path(__file__).resolve().parents[1]
    api = (root / "app/api/v1/trend_collections.py").read_text(encoding="utf-8")
    client = (root / "frontend/mini-app/lib/trend-collections-api.ts").read_text(encoding="utf-8")
    ui = (root / "frontend/mini-app/components/trend-collection-admin.tsx").read_text(encoding="utf-8")

    assert "hashtags: list[str]" in api
    assert "TrendCollectionService.delete_collection(" in api
    assert '"operation": "trend_collection.delete"' in api
    assert "remove: (id: string)" in client
    assert 'method: "DELETE"' in client
    assert "Хэштеги категории" in ui
    assert "hashtags: parseTags(draft.hashtags)" in ui
    assert "trendCollectionsApi.remove(folder.id)" in ui
    assert "Удалить категорию" in ui
