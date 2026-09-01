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
    """Admin-owned folders for curated ROXY templates."""

    SETTING_KEY = "trend_collections_v1"
    DEFAULT_COLLECTION_ID = "trends"
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
            # Internal aliases keep creator-facing folder copy clean while allowing
            # short hashtags such as #др to route templates automatically.
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
        if tag.startswith("#"):
            tag = tag[1:]
        tag = tag.strip()
        if not tag or len(tag) > 40 or not re.fullmatch(r"[\w-]+", tag, re.UNICODE):
            return ""
        return tag

    @classmethod
    def collection_hashtags(cls, collection: dict[str, Any]) -> set[str]:
        text = " ".join(
            str(collection.get(field) or "")
            for field in ("title", "description")
        )
        result = {
            normalized
            for raw in cls._HASHTAG_RE.findall(text)
            if (normalized := cls.normalize_hashtag(raw))
        }
        aliases = collection.get("aliases")
        if isinstance(aliases, list):
            result.update(
                normalized
                for raw in aliases
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
            raise TrendCollectionError("Folder title must contain 1..80 characters")
        description = str(raw.get("description") or "").strip()
        if len(description) > 240:
            raise TrendCollectionError("Folder description must be at most 240 characters")
        sort_order = int(raw.get("sort_order", 100))
        if sort_order < -100_000 or sort_order > 100_000:
            raise TrendCollectionError("Folder sort_order is out of range")

        raw_aliases = raw.get("aliases")
        aliases: list[str] = []
        if isinstance(raw_aliases, list):
            seen: set[str] = set()
            for value in raw_aliases:
                alias = cls.normalize_hashtag(value)
                if alias and alias not in seen:
                    seen.add(alias)
                    aliases.append(alias)

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
        return normalized

    @classmethod
    def merge_state(cls, raw: dict[str, Any] | None) -> dict[str, Any]:
        value = raw if isinstance(raw, dict) else {}
        stored = value.get("collections")
        stored_items = stored if isinstance(stored, list) else []
        by_id: dict[str, dict[str, Any]] = {item["id"]: item for item in cls.default_collections()}
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
            "schema_version": 1,
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
        state["collections"] = collections
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
        state = await cls.state(session)
        existing = next((item for item in state["collections"] if item["id"] == collection_id), None)
        if existing is None:
            raise LookupError("Folder not found")
        return await cls.upsert_collection(
            session,
            admin_id=admin_id,
            collection_id=collection_id,
            payload={**existing, "is_active": active},
        )

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
        if not any(item["id"] == collection_id for item in state["collections"]):
            raise LookupError("Folder not found")
        tid = str(trend_id)
        state["assignments"][tid] = collection_id
        auto = set(state.get("auto_assignments") or [])
        if automatic:
            auto.add(tid)
        else:
            auto.discard(tid)
        state["auto_assignments"] = sorted(auto)
        setting.value = state
        setting.updated_by_admin_id = admin_id
        await session.flush()
        return {"trend_id": tid, "collection_id": collection_id}

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
