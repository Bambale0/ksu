from __future__ import annotations

import re
import uuid
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminTrend, TrendCollection, TrendCollectionAssignment


class TrendCollectionError(ValueError):
    pass


class TrendCollectionService:
    """Admin-owned categories for curated ROXY templates."""

    # Kept only as the identifier of the legacy JSON source copied by migration 0036.
    SETTING_KEY = "trend_collections_v1"
    DEFAULT_COLLECTION_ID = "trends"
    SCHEMA_VERSION = 2
    MAX_HASHTAGS = 24
    _ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
    _HASHTAG_RE = re.compile(r"(?<!\w)#([\w-]{1,40})", re.UNICODE)
    DEFAULTS: tuple[dict[str, Any], ...] = (
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

    @classmethod
    def default_collections(cls) -> list[dict[str, Any]]:
        return [dict(item) for item in cls.DEFAULTS]

    @classmethod
    def normalize_hashtag(cls, value: object) -> str:
        tag = str(value or "").strip().casefold()
        tag = tag.lstrip("#").strip()
        if not tag or len(tag) > 40 or not re.fullmatch(r"[\w-]+", tag, re.UNICODE):
            return ""
        return tag

    @classmethod
    def collection_hashtags(cls, collection: dict[str, Any]) -> set[str]:
        text = " ".join(str(collection.get(field) or "") for field in ("title", "description"))
        result = {
            normalized
            for raw in cls._HASHTAG_RE.findall(text)
            if (normalized := cls.normalize_hashtag(raw))
        }
        raw_aliases = collection.get("aliases")
        if isinstance(raw_aliases, list):
            result.update(
                normalized
                for raw in raw_aliases
                if (normalized := cls.normalize_hashtag(raw))
            )
        return result

    @classmethod
    def matching_collection(cls, state: dict[str, Any], tags: Iterable[object]) -> str | None:
        normalized_tags = {
            normalized
            for raw in tags
            if (normalized := cls.normalize_hashtag(raw))
        }
        if not normalized_tags:
            return None
        collections = state.get("collections") if isinstance(state, dict) else []
        if not isinstance(collections, list):
            return None
        for collection in collections:
            if not isinstance(collection, dict):
                continue
            collection_id = str(collection.get("id") or "").strip().lower()
            if collection_id == cls.DEFAULT_COLLECTION_ID or not bool(collection.get("is_active", True)):
                continue
            if normalized_tags.intersection(cls.collection_hashtags(collection)):
                return collection_id
        return None

    @classmethod
    def normalize_collection(
        cls,
        raw: dict[str, Any],
        *,
        collection_id: str | None = None,
        system_key: str | None = None,
    ) -> dict[str, Any]:
        cid = str(collection_id or raw.get("id") or "").strip().lower()
        if not cid:
            cid = f"folder-{uuid.uuid4().hex[:12]}"
        if not cls._ID_RE.fullmatch(cid):
            raise TrendCollectionError("Invalid collection id")
        title = str(raw.get("title") or "").strip()
        if not title or len(title) > 80:
            raise TrendCollectionError("Название категории должно содержать от 1 до 80 символов")
        description = str(raw.get("description") or "").strip()
        if len(description) > 240:
            raise TrendCollectionError("Описание категории не должно превышать 240 символов")
        sort_order = int(raw.get("sort_order", 100))
        if sort_order < -100_000 or sort_order > 100_000:
            raise TrendCollectionError("Некорректный порядок категории")

        raw_aliases = raw.get("aliases")
        if not isinstance(raw_aliases, list):
            raw_aliases = raw.get("hashtags")
        aliases: list[str] = []
        if isinstance(raw_aliases, list):
            seen: set[str] = set()
            for value in raw_aliases:
                alias = cls.normalize_hashtag(value)
                if not alias:
                    raise TrendCollectionError(f"Некорректный хэштег: {value}")
                if alias not in seen:
                    seen.add(alias)
                    aliases.append(alias)
        if len(aliases) > cls.MAX_HASHTAGS:
            raise TrendCollectionError(f"В категории может быть не больше {cls.MAX_HASHTAGS} хэштегов")

        normalized = {
            "id": cid,
            "system_key": system_key if system_key is not None else raw.get("system_key"),
            "title": title,
            "description": description,
            "aliases": aliases,
            "sort_order": sort_order,
            "is_active": bool(raw.get("is_active", True)),
        }
        if normalized["system_key"] is not None:
            normalized["system_key"] = str(normalized["system_key"]).strip() or None
        if cid == cls.DEFAULT_COLLECTION_ID:
            normalized["system_key"] = "trends"
            normalized["is_active"] = True
            normalized["aliases"] = []
        return normalized

    @classmethod
    def _validate_unique_hashtags(cls, collections: Iterable[dict[str, Any]]) -> None:
        owner_by_tag: dict[str, dict[str, Any]] = {}
        for collection in collections:
            if str(collection.get("id") or "") == cls.DEFAULT_COLLECTION_ID:
                continue
            for tag in cls.collection_hashtags(collection):
                owner = owner_by_tag.get(tag)
                if owner is not None and owner.get("id") != collection.get("id"):
                    raise TrendCollectionError(
                        f"Хэштег #{tag} уже используется категорией «{owner.get('title') or owner.get('id')}»"
                    )
                owner_by_tag[tag] = collection

    @classmethod
    def merge_state(cls, raw: dict[str, Any] | None) -> dict[str, Any]:
        """Normalize the legacy JSON shape used by migration/backward-compatible tests."""

        value = raw if isinstance(raw, dict) else {}
        stored = value.get("collections")
        stored_items = stored if isinstance(stored, list) else []

        initialized = bool(value.get("initialized")) or int(value.get("schema_version") or 0) >= cls.SCHEMA_VERSION
        defaults = cls.default_collections()
        if initialized:
            root = next(item for item in defaults if item["id"] == cls.DEFAULT_COLLECTION_ID)
            by_id: dict[str, dict[str, Any]] = {root["id"]: root}
        else:
            by_id = {item["id"]: item for item in defaults}

        for item in stored_items:
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or "").strip().lower()
            if not cid or not cls._ID_RE.fullmatch(cid):
                continue
            base = by_id.get(cid, {})
            try:
                by_id[cid] = cls.normalize_collection(
                    {**base, **item},
                    collection_id=cid,
                    system_key=base.get("system_key") or item.get("system_key"),
                )
            except TrendCollectionError:
                continue

        assignments_raw = value.get("assignments")
        assignments: dict[str, str] = {}
        if isinstance(assignments_raw, dict):
            for trend_id, collection_id in assignments_raw.items():
                tid = str(trend_id or "").strip()
                cid = str(collection_id or "").strip().lower()
                if tid and cid in by_id:
                    assignments[tid] = cid

        auto_raw = value.get("auto_assignments")
        auto_assignments: list[str] = []
        if isinstance(auto_raw, list):
            auto_assignments = sorted(
                {
                    str(trend_id).strip()
                    for trend_id in auto_raw
                    if str(trend_id).strip() in assignments
                }
            )

        collections = sorted(
            by_id.values(),
            key=lambda item: (int(item.get("sort_order", 0)), str(item.get("title", "")).casefold()),
        )
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "initialized": True,
            "collections": collections,
            "assignments": assignments,
            "auto_assignments": auto_assignments,
        }

    @staticmethod
    def _collection_view(item: TrendCollection) -> dict[str, Any]:
        aliases = item.aliases if isinstance(item.aliases, list) else []
        return {
            "id": item.id,
            "system_key": item.system_key,
            "title": item.title,
            "description": item.description,
            "aliases": list(aliases),
            "sort_order": item.sort_order,
            "is_active": item.is_active,
        }

    @classmethod
    async def state(cls, session: AsyncSession) -> dict[str, Any]:
        collections = list(
            (
                await session.scalars(
                    select(TrendCollection).order_by(
                        TrendCollection.sort_order.asc(),
                        TrendCollection.title.asc(),
                    )
                )
            ).all()
        )
        if not collections:
            # Migration 0036 seeds relational defaults. This fallback keeps read
            # behavior safe during tests or a partially initialized environment
            # without silently writing from a public GET path.
            return cls.merge_state(None)

        assignment_rows = list((await session.scalars(select(TrendCollectionAssignment))).all())
        assignments = {
            str(item.trend_id): item.collection_id
            for item in assignment_rows
        }
        auto_assignments = sorted(
            str(item.trend_id)
            for item in assignment_rows
            if item.automatic
        )
        return {
            "schema_version": cls.SCHEMA_VERSION,
            "initialized": True,
            "collections": [cls._collection_view(item) for item in collections],
            "assignments": assignments,
            "auto_assignments": auto_assignments,
        }

    @classmethod
    async def _lock_mutations(cls, session: AsyncSession) -> TrendCollection:
        root = await session.scalar(
            select(TrendCollection)
            .where(TrendCollection.id == cls.DEFAULT_COLLECTION_ID)
            .with_for_update()
        )
        if root is not None:
            return root

        # Defensive bootstrap only. Normal installations receive these rows from
        # migration 0036. Mutations serialize on the mandatory root row.
        for payload in cls.default_collections():
            normalized = cls.normalize_collection(payload, collection_id=str(payload["id"]))
            session.add(
                TrendCollection(
                    id=normalized["id"],
                    system_key=normalized["system_key"],
                    title=normalized["title"],
                    description=normalized["description"],
                    aliases=normalized["aliases"],
                    sort_order=normalized["sort_order"],
                    is_active=normalized["is_active"],
                )
            )
        await session.flush()
        root = await session.get(TrendCollection, cls.DEFAULT_COLLECTION_ID)
        if root is None:
            raise RuntimeError("Trend collection root could not be initialized")
        return root

    @classmethod
    async def upsert_collection(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        payload: dict[str, Any],
        collection_id: str | None = None,
    ) -> dict[str, Any]:
        del admin_id
        await cls._lock_mutations(session)
        cid = str(collection_id or payload.get("id") or "").strip().lower() or None
        existing = await session.get(TrendCollection, cid) if cid else None
        existing_view = cls._collection_view(existing) if existing is not None else {}
        normalized = cls.normalize_collection(
            {**existing_view, **payload},
            collection_id=cid,
            system_key=existing.system_key if existing is not None else None,
        )

        rows = list((await session.scalars(select(TrendCollection))).all())
        candidate = [
            cls._collection_view(row)
            for row in rows
            if row.id != normalized["id"]
        ]
        candidate.append(normalized)
        cls._validate_unique_hashtags(candidate)

        if existing is None:
            existing = TrendCollection(id=normalized["id"])
            session.add(existing)
        existing.system_key = normalized["system_key"]
        existing.title = normalized["title"]
        existing.description = normalized["description"]
        existing.aliases = normalized["aliases"]
        existing.sort_order = normalized["sort_order"]
        existing.is_active = normalized["is_active"]
        await session.flush()
        return normalized

    @classmethod
    async def set_collection_active(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        collection_id: str,
        active: bool,
    ) -> dict[str, Any]:
        cid = str(collection_id or "").strip().lower()
        if cid == cls.DEFAULT_COLLECTION_ID and not active:
            raise TrendCollectionError("Категорию «Тренды» нельзя скрыть")
        existing = await session.get(TrendCollection, cid)
        if existing is None:
            raise LookupError("Folder not found")
        return await cls.upsert_collection(
            session,
            admin_id=admin_id,
            collection_id=cid,
            payload={**cls._collection_view(existing), "is_active": active},
        )

    @classmethod
    async def delete_collection(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        collection_id: str,
    ) -> dict[str, Any]:
        del admin_id
        cid = str(collection_id or "").strip().lower()
        if cid == cls.DEFAULT_COLLECTION_ID:
            raise TrendCollectionError("Категорию «Тренды» нельзя удалить")

        await cls._lock_mutations(session)
        existing = await session.scalar(
            select(TrendCollection).where(TrendCollection.id == cid).with_for_update()
        )
        if existing is None:
            raise LookupError("Folder not found")

        affected = list(
            (
                await session.scalars(
                    select(TrendCollectionAssignment)
                    .where(TrendCollectionAssignment.collection_id == cid)
                    .with_for_update()
                )
            ).all()
        )
        affected_auto = [item.trend_id for item in affected if item.automatic]
        title = existing.title
        await session.delete(existing)
        await session.flush()

        reassigned = 0
        if affected_auto:
            state = await cls.state(session)
            trends = list(
                (
                    await session.scalars(
                        select(AdminTrend).where(AdminTrend.id.in_(affected_auto))
                    )
                ).all()
            )
            for trend in trends:
                payload = trend.payload if isinstance(trend.payload, dict) else {}
                tags = payload.get("tags") or []
                if isinstance(tags, str):
                    tags = [tags]
                target = cls.matching_collection(state, tags)
                if target:
                    session.add(
                        TrendCollectionAssignment(
                            trend_id=trend.id,
                            collection_id=target,
                            automatic=True,
                        )
                    )
                    reassigned += 1
            await session.flush()

        return {
            "id": cid,
            "title": title or cid,
            "deleted": True,
            "released_items": len(affected),
            "auto_reassigned": reassigned,
        }

    @classmethod
    async def assign_trend(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        trend_id: uuid.UUID,
        collection_id: str,
        automatic: bool = False,
    ) -> dict[str, str]:
        del admin_id
        await cls._lock_mutations(session)
        trend = await session.get(AdminTrend, trend_id)
        if trend is None:
            raise LookupError("Trend not found")
        cid = str(collection_id or "").strip().lower()
        collection = await session.get(TrendCollection, cid)
        if collection is None:
            raise LookupError("Folder not found")

        assignment = await session.scalar(
            select(TrendCollectionAssignment)
            .where(TrendCollectionAssignment.trend_id == trend_id)
            .with_for_update()
        )
        if assignment is None:
            assignment = TrendCollectionAssignment(
                trend_id=trend_id,
                collection_id=cid,
                automatic=automatic,
            )
            session.add(assignment)
        else:
            assignment.collection_id = cid
            assignment.automatic = automatic
        await session.flush()
        return {"trend_id": str(trend_id), "collection_id": cid}

    @classmethod
    async def _clear_auto_assignment(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        trend_id: uuid.UUID,
    ) -> bool:
        del admin_id
        await cls._lock_mutations(session)
        assignment = await session.scalar(
            select(TrendCollectionAssignment)
            .where(TrendCollectionAssignment.trend_id == trend_id)
            .with_for_update()
        )
        if assignment is None or not assignment.automatic:
            return False
        await session.delete(assignment)
        await session.flush()
        return True

    @classmethod
    async def assign_from_tags(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        trend_id: uuid.UUID,
        tags: Iterable[object],
    ) -> str | None:
        del admin_id
        await cls._lock_mutations(session)
        assignment = await session.scalar(
            select(TrendCollectionAssignment)
            .where(TrendCollectionAssignment.trend_id == trend_id)
            .with_for_update()
        )

        # A manual move is authoritative. Editing the recipe must not silently
        # convert that assignment into an automatic one just because a tag still
        # happens to match the same (or another) category.
        if assignment is not None and not assignment.automatic:
            return assignment.collection_id

        state = await cls.state(session)
        collection_id = cls.matching_collection(state, tags)
        if collection_id is None:
            if assignment is not None:
                await session.delete(assignment)
                await session.flush()
            return None

        if assignment is None:
            assignment = TrendCollectionAssignment(
                trend_id=trend_id,
                collection_id=collection_id,
                automatic=True,
            )
            session.add(assignment)
        else:
            assignment.collection_id = collection_id
            assignment.automatic = True
        await session.flush()
        return collection_id

    @classmethod
    def assigned_collection(cls, state: dict[str, Any], trend_id: uuid.UUID | str) -> str:
        assignments = state.get("assignments") if isinstance(state, dict) else {}
        if isinstance(assignments, dict):
            value = str(assignments.get(str(trend_id)) or "").strip().lower()
            if value:
                return value
        return cls.DEFAULT_COLLECTION_ID
