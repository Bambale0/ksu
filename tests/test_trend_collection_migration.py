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
