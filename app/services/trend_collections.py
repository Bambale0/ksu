from __future__ import annotations

import re
import uuid
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminRuntimeSetting, AdminTrend


class TrendCollectionError(ValueError):
    pass


class TrendCollectionService:
    """Admin-owned categories for curated ROXY templates."""

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
        value = raw if isinstance(raw, dict) else {}
        stored = value.get("collections")
        stored_items = stored if isinstance(stored, list) else []

        # Schema v1 always re-seeded defaults, so deleting "birthday" made it
        # reappear. An initialized v2 state is authoritative: only the mandatory
        # live-trends root is seeded, every other category is genuinely admin-owned.
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

    @classmethod
    async def state(cls, session: AsyncSession) -> dict[str, Any]:
        item = await session.get(AdminRuntimeSetting, cls.SETTING_KEY)
        return cls.merge_state(item.value if item else None)

    @classmethod
    async def _locked_setting(cls, session: AsyncSession, *, admin_id: uuid.UUID) -> AdminRuntimeSetting:
        item = await session.scalar(
            select(AdminRuntimeSetting)
            .where(AdminRuntimeSetting.key == cls.SETTING_KEY)
            .with_for_update()
        )
        if item is None:
            item = AdminRuntimeSetting(
                key=cls.SETTING_KEY,
                value=cls.merge_state(None),
                updated_by_admin_id=admin_id,
            )
            session.add(item)
            await session.flush()
        return item

    @classmethod
    async def upsert_collection(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        payload: dict[str, Any],
        collection_id: str | None = None,
    ) -> dict[str, Any]:
        setting = await cls._locked_setting(session, admin_id=admin_id)
        state = cls.merge_state(setting.value)
        existing = next((item for item in state["collections"] if item["id"] == collection_id), None)
        system_key = existing.get("system_key") if existing else None
        normalized = cls.normalize_collection(
            {**(existing or {}), **payload},
            collection_id=collection_id,
            system_key=system_key,
        )
        collections = [item for item in state["collections"] if item["id"] != normalized["id"]]
        collections.append(normalized)
        cls._validate_unique_hashtags(collections)
        state["collections"] = collections
        state["initialized"] = True
        setting.value = cls.merge_state(state)
        setting.updated_by_admin_id = admin_id
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
        state = await cls.state(session)
        existing = next((item for item in state["collections"] if item["id"] == cid), None)
        if existing is None:
            raise LookupError("Folder not found")
        return await cls.upsert_collection(
            session,
            admin_id=admin_id,
            collection_id=cid,
            payload={**existing, "is_active": active},
        )

    @classmethod
    async def delete_collection(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        collection_id: str,
    ) -> dict[str, Any]:
        cid = str(collection_id or "").strip().lower()
        if cid == cls.DEFAULT_COLLECTION_ID:
            raise TrendCollectionError("Категорию «Тренды» нельзя удалить")

        setting = await cls._locked_setting(session, admin_id=admin_id)
        state = cls.merge_state(setting.value)
        existing = next((item for item in state["collections"] if item["id"] == cid), None)
        if existing is None:
            raise LookupError("Folder not found")

        assignments = state["assignments"]
        auto = set(state.get("auto_assignments") or [])
        affected = [tid for tid, target in assignments.items() if target == cid]
        affected_auto = {tid for tid in affected if tid in auto}
        for tid in affected:
            assignments.pop(tid, None)
            auto.discard(tid)

        state["collections"] = [item for item in state["collections"] if item["id"] != cid]
        state["auto_assignments"] = sorted(auto)
        state["initialized"] = True
        state = cls.merge_state(state)

        reassigned = 0
        trend_ids: list[uuid.UUID] = []
        for tid in affected_auto:
            try:
                trend_ids.append(uuid.UUID(tid))
            except (TypeError, ValueError):
                continue
        if trend_ids:
            rows = list((await session.scalars(select(AdminTrend).where(AdminTrend.id.in_(trend_ids)))).all())
            auto = set(state.get("auto_assignments") or [])
            for trend in rows:
                payload = trend.payload if isinstance(trend.payload, dict) else {}
                tags = payload.get("tags") or []
                if isinstance(tags, str):
                    tags = [tags]
                target = cls.matching_collection(state, tags)
                if target:
                    tid = str(trend.id)
                    state["assignments"][tid] = target
                    auto.add(tid)
                    reassigned += 1
            state["auto_assignments"] = sorted(auto)

        setting.value = cls.merge_state(state)
        setting.updated_by_admin_id = admin_id
        await session.flush()
        return {
            "id": cid,
            "title": existing.get("title") or cid,
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
        trend = await session.get(AdminTrend, trend_id)
        if trend is None:
            raise LookupError("Trend not found")
        setting = await cls._locked_setting(session, admin_id=admin_id)
        state = cls.merge_state(setting.value)
        cid = str(collection_id or "").strip().lower()
        if not any(item["id"] == cid for item in state["collections"]):
            raise LookupError("Folder not found")
        tid = str(trend_id)
        state["assignments"][tid] = cid
        auto = set(state.get("auto_assignments") or [])
        if automatic:
            auto.add(tid)
        else:
            auto.discard(tid)
        state["auto_assignments"] = sorted(auto)
        setting.value = state
        setting.updated_by_admin_id = admin_id
        await session.flush()
        return {"trend_id": tid, "collection_id": cid}

    @classmethod
    async def _clear_auto_assignment(
        cls,
        session: AsyncSession,
        *,
        admin_id: uuid.UUID,
        trend_id: uuid.UUID,
    ) -> bool:
        setting = await cls._locked_setting(session, admin_id=admin_id)
        state = cls.merge_state(setting.value)
        tid = str(trend_id)
        auto = set(state.get("auto_assignments") or [])
        if tid not in auto:
            return False
        state["assignments"].pop(tid, None)
        auto.discard(tid)
        state["auto_assignments"] = sorted(auto)
        setting.value = state
        setting.updated_by_admin_id = admin_id
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
        setting = await cls._locked_setting(session, admin_id=admin_id)
        state = cls.merge_state(setting.value)
        tid = str(trend_id)
        assignments = state["assignments"]
        auto = set(state.get("auto_assignments") or [])
        current = str(assignments.get(tid) or "").strip().lower()

        # A manual move is authoritative. Editing the recipe must not silently
        # convert that assignment into an automatic one just because a tag still
        # happens to match the same (or another) collection.
        if current and tid not in auto:
            return current

        collection_id = cls.matching_collection(state, tags)
        if collection_id is None:
            if tid not in auto:
                return None
            assignments.pop(tid, None)
            auto.discard(tid)
        else:
            assignments[tid] = collection_id
            auto.add(tid)

        state["auto_assignments"] = sorted(auto)
        setting.value = state
        setting.updated_by_admin_id = admin_id
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
