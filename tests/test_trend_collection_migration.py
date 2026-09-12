from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "0036_trend_collections_relational.py"


def _migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("trend_collections_relational_migration", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v2_backfill_preserves_deleted_default_and_valid_assignments() -> None:
    module = _migration_module()
    trend_id = str(uuid.uuid4())
    collections, assignments, automatic = module._merged_legacy_state(
        {
            "schema_version": 2,
            "initialized": True,
            "collections": [
                {
                    "id": "party",
                    "title": "Party",
                    "description": "",
                    "aliases": ["#PARTY"],
                    "sort_order": 20,
                    "is_active": True,
                }
            ],
            "assignments": {
                trend_id: "party",
                str(uuid.uuid4()): "missing",
            },
            "auto_assignments": [trend_id],
        }
    )

    assert [item["id"] for item in collections] == ["trends", "party"]
    assert "birthday" not in {item["id"] for item in collections}
    assert next(item for item in collections if item["id"] == "party")["aliases"] == ["party"]
    assert assignments == {trend_id: "party"}
    assert automatic == {trend_id}


def test_v1_backfill_seeds_legacy_defaults() -> None:
    module = _migration_module()
    collections, assignments, automatic = module._merged_legacy_state(
        {"schema_version": 1, "collections": []}
    )

    assert [item["id"] for item in collections] == ["trends", "birthday"]
    assert assignments == {}
    assert automatic == set()


def test_relational_state_serializes_back_to_legacy_shape_for_downgrade() -> None:
    module = _migration_module()
    trend_id = uuid.uuid4()
    state = module._legacy_state_from_relational(
        [
            {
                "id": "party",
                "system_key": None,
                "title": "Party",
                "description": "Ideas",
                "aliases": ["party"],
                "sort_order": 20,
                "is_active": False,
            },
            {
                "id": "trends",
                "system_key": "trends",
                "title": "Тренды",
                "description": "Live",
                "aliases": [],
                "sort_order": 0,
                "is_active": True,
            },
        ],
        [
            {
                "trend_id": trend_id,
                "collection_id": "party",
                "automatic": True,
            }
        ],
    )

    assert [item["id"] for item in state["collections"]] == ["trends", "party"]
    assert state["assignments"] == {str(trend_id): "party"}
    assert state["auto_assignments"] == [str(trend_id)]
    assert state["collections"][1]["is_active"] is False
