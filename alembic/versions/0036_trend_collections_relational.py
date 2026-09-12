"""normalize trend collections into relational tables

Revision ID: 0036_trend_collections
Revises: 0035_generation_integrity
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0036_trend_collections"
down_revision: str | None = "0035_generation_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SETTING_KEY = "trend_collections_v1"
_ROOT_ID = "trends"
_SCHEMA_VERSION = 2
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_TAG_RE = re.compile(r"^[\w-]{1,40}$", re.UNICODE)

_DEFAULTS: tuple[dict[str, Any], ...] = (
    {
        "id": "trends",
        "system_key": "trends",
        "title": "Тренды",
        "description": "То, что сейчас гуляет в Instagram",
        "aliases": [],
        "sort_order": 0,
        "is_active": True,
    },
    {
        "id": "birthday",
        "system_key": "birthday",
        "title": "День рождения",
        "description": "Фото и видео для поздравлений и праздничных сюжетов",
        "aliases": ["др", "деньрождения", "день-рождения", "день_рождения", "birthday"],
        "sort_order": 10,
        "is_active": True,
    },
)


def _normalize_aliases(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in raw:
        alias = str(value or "").strip().casefold().lstrip("#").strip()
        if not alias or not _TAG_RE.fullmatch(alias) or alias in seen:
            continue
        seen.add(alias)
        result.append(alias)
    return result[:24]


def _normalize_collection(raw: dict[str, Any], *, collection_id: str) -> dict[str, Any] | None:
    if not _ID_RE.fullmatch(collection_id):
        return None
    title = str(raw.get("title") or "").strip()
    if not title or len(title) > 80:
        return None
    description = str(raw.get("description") or "").strip()[:240]
    try:
        sort_order = int(raw.get("sort_order", 100))
    except (TypeError, ValueError):
        sort_order = 100
    sort_order = max(-100_000, min(100_000, sort_order))
    system_key = str(raw.get("system_key") or "").strip() or None
    aliases = _normalize_aliases(raw.get("aliases", raw.get("hashtags")))
    is_active = bool(raw.get("is_active", True))
    if collection_id == _ROOT_ID:
        system_key = "trends"
        aliases = []
        is_active = True
    return {
        "id": collection_id,
        "system_key": system_key,
        "title": title,
        "description": description,
        "aliases": aliases,
        "sort_order": sort_order,
        "is_active": is_active,
    }


def _merged_legacy_state(raw: object) -> tuple[list[dict[str, Any]], dict[str, str], set[str]]:
    value = raw if isinstance(raw, dict) else {}
    initialized = bool(value.get("initialized")) or int(value.get("schema_version") or 0) >= _SCHEMA_VERSION

    defaults = [dict(item) for item in _DEFAULTS]
    if initialized:
        root = next(item for item in defaults if item["id"] == _ROOT_ID)
        by_id: dict[str, dict[str, Any]] = {_ROOT_ID: root}
    else:
        by_id = {item["id"]: item for item in defaults}

    stored = value.get("collections")
    if isinstance(stored, list):
        for item in stored:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or "").strip().lower()
            base = by_id.get(cid, {})
            normalized = _normalize_collection(
                {**base, **item},
                collection_id=cid,
            )
            if normalized is not None:
                by_id[cid] = normalized

    # Keep system keys unique even if a malformed legacy blob contains duplicates.
    seen_system_keys: set[str] = set()
    collections: list[dict[str, Any]] = []
    for item in sorted(
        by_id.values(),
        key=lambda entry: (int(entry.get("sort_order", 0)), str(entry.get("title") or "").casefold()),
    ):
        system_key = item.get("system_key")
        if system_key and system_key in seen_system_keys:
            item = {**item, "system_key": None}
        elif system_key:
            seen_system_keys.add(str(system_key))
        collections.append(item)

    valid_ids = {item["id"] for item in collections}
    assignments: dict[str, str] = {}
    raw_assignments = value.get("assignments")
    if isinstance(raw_assignments, dict):
        for trend_id, collection_id in raw_assignments.items():
            tid = str(trend_id or "").strip()
            cid = str(collection_id or "").strip().lower()
            if tid and cid in valid_ids:
                assignments[tid] = cid

    automatic: set[str] = set()
    raw_auto = value.get("auto_assignments")
    if isinstance(raw_auto, list):
        automatic = {
            str(trend_id).strip()
            for trend_id in raw_auto
            if str(trend_id).strip() in assignments
        }
    return collections, assignments, automatic


def _legacy_state_from_relational(
    collections: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_collections = sorted(
        (
            {
                "id": str(item["id"]),
                "system_key": item.get("system_key"),
                "title": str(item["title"]),
                "description": str(item.get("description") or ""),
                "aliases": list(item.get("aliases") or []),
                "sort_order": int(item.get("sort_order") or 0),
                "is_active": bool(item.get("is_active", True)),
            }
            for item in collections
        ),
        key=lambda item: (item["sort_order"], item["title"].casefold(), item["id"]),
    )
    assignment_map = {
        str(item["trend_id"]): str(item["collection_id"])
        for item in assignments
    }
    automatic = sorted(
        str(item["trend_id"])
        for item in assignments
        if bool(item.get("automatic"))
    )
    return {
        "schema_version": _SCHEMA_VERSION,
        "initialized": True,
        "collections": ordered_collections,
        "assignments": assignment_map,
        "auto_assignments": automatic,
    }


def upgrade() -> None:
    op.create_table(
        "trend_collections",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("system_key", sa.String(length=64), nullable=True),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trend_collections_active_order",
        "trend_collections",
        ["is_active", "sort_order"],
        unique=False,
    )
    op.create_index(
        "uq_trend_collections_system_key",
        "trend_collections",
        ["system_key"],
        unique=True,
        postgresql_where=sa.text("system_key IS NOT NULL"),
    )

    op.create_table(
        "trend_collection_assignments",
        sa.Column("trend_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.String(length=64), nullable=False),
        sa.Column("automatic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["trend_collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trend_id"], ["admin_trends.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("trend_id"),
    )
    op.create_index(
        "ix_trend_collection_assignments_collection",
        "trend_collection_assignments",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        "ix_trend_collection_assignments_auto_collection",
        "trend_collection_assignments",
        ["automatic", "collection_id"],
        unique=False,
    )

    bind = op.get_bind()
    row = bind.execute(
        sa.text("SELECT value FROM admin_runtime_settings WHERE key = :key"),
        {"key": _SETTING_KEY},
    ).first()
    legacy_value = row[0] if row is not None else None
    collections, assignments, automatic = _merged_legacy_state(legacy_value)

    collection_table = sa.table(
        "trend_collections",
        sa.column("id", sa.String()),
        sa.column("system_key", sa.String()),
        sa.column("title", sa.String()),
        sa.column("description", sa.String()),
        sa.column("aliases", sa.JSON()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    if collections:
        bind.execute(sa.insert(collection_table), collections)

    existing_trends = {
        str(item[0])
        for item in bind.execute(sa.text("SELECT id FROM admin_trends")).all()
    }
    assignment_rows = [
        {
            "trend_id": uuid.UUID(trend_id),
            "collection_id": collection_id,
            "automatic": trend_id in automatic,
        }
        for trend_id, collection_id in assignments.items()
        if trend_id in existing_trends
    ]
    if assignment_rows:
        assignment_table = sa.table(
            "trend_collection_assignments",
            sa.column("trend_id", sa.Uuid()),
            sa.column("collection_id", sa.String()),
            sa.column("automatic", sa.Boolean()),
        )
        bind.execute(sa.insert(assignment_table), assignment_rows)


def downgrade() -> None:
    bind = op.get_bind()

    # Preserve any category edits made after upgrade before returning to the
    # legacy JSON-backed runtime. Clean installs without the legacy row simply
    # fall back to the old service defaults after downgrade.
    legacy_exists = bind.execute(
        sa.text("SELECT 1 FROM admin_runtime_settings WHERE key = :key"),
        {"key": _SETTING_KEY},
    ).first()
    if legacy_exists is not None:
        collections = [
            dict(row._mapping)
            for row in bind.execute(
                sa.text(
                    """
                    SELECT id, system_key, title, description, aliases, sort_order, is_active
                    FROM trend_collections
                    """
                )
            ).all()
        ]
        assignments = [
            dict(row._mapping)
            for row in bind.execute(
                sa.text(
                    """
                    SELECT trend_id, collection_id, automatic
                    FROM trend_collection_assignments
                    """
                )
            ).all()
        ]
        legacy_state = _legacy_state_from_relational(collections, assignments)
        settings_table = sa.table(
            "admin_runtime_settings",
            sa.column("key", sa.String()),
            sa.column("value", sa.JSON()),
        )
        bind.execute(
            sa.update(settings_table)
            .where(settings_table.c.key == _SETTING_KEY)
            .values(value=legacy_state)
        )

    op.drop_index(
        "ix_trend_collection_assignments_auto_collection",
        table_name="trend_collection_assignments",
    )
    op.drop_index(
        "ix_trend_collection_assignments_collection",
        table_name="trend_collection_assignments",
    )
    op.drop_table("trend_collection_assignments")
    op.drop_index("uq_trend_collections_system_key", table_name="trend_collections")
    op.drop_index("ix_trend_collections_active_order", table_name="trend_collections")
    op.drop_table("trend_collections")
