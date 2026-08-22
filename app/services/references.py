from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reference_models import UserReference


class ReferenceError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReferenceService:
    KINDS = {"image", "video", "audio"}
    MAX_PER_KIND = 12

    @staticmethod
    def _safe_url(value: str) -> str:
        value = value.strip()
        if len(value) > 4000:
            raise ReferenceError("Reference URL is too long")
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ReferenceError("Reference URL must be HTTPS")
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            raise ReferenceError("Local reference URLs are not allowed")
        return value

    @staticmethod
    def _safe_hash(value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return None
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise ReferenceError("Reference hash must be SHA-256")
        return normalized

    @classmethod
    async def get_by_hash(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        kind: str,
        file_hash: str,
        include_deleted: bool = False,
    ) -> UserReference | None:
        if kind not in cls.KINDS:
            raise ReferenceError("Unsupported reference kind")
        safe_hash = cls._safe_hash(file_hash)
        if not safe_hash:
            return None
        stmt = select(UserReference).where(
            UserReference.user_id == user_id,
            UserReference.kind == kind,
            UserReference.file_hash == safe_hash,
        )
        if not include_deleted:
            stmt = stmt.where(UserReference.status == "ready")
        return await session.scalar(stmt)

    @classmethod
    async def _find_existing(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        source_url: str,
        kind: str,
        file_hash: str | None,
    ) -> UserReference | None:
        conditions = [UserReference.source_url == source_url]
        if file_hash:
            conditions.append(
                (UserReference.kind == kind) & (UserReference.file_hash == file_hash)
            )
        return await session.scalar(
            select(UserReference).where(
                UserReference.user_id == user_id,
                or_(*conditions),
            )
        )

    @classmethod
    async def _prune_kind(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        kind: str,
        keep_latest: int | None = None,
    ) -> int:
        keep = max(1, int(keep_latest or cls.MAX_PER_KIND))
        stale = list(
            (
                await session.scalars(
                    select(UserReference)
                    .where(
                        UserReference.user_id == user_id,
                        UserReference.kind == kind,
                        UserReference.status == "ready",
                    )
                    .order_by(
                        UserReference.last_used_at.desc().nullslast(),
                        UserReference.created_at.desc(),
                        UserReference.id.desc(),
                    )
                    .offset(keep)
                )
            ).all()
        )
        for row in stale:
            row.status = "deleted"
        return len(stale)

    @classmethod
    async def register(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        source_url: str,
        kind: str,
        label: str = "",
        original_filename: str | None = None,
        content_type: str | None = None,
        file_hash: str | None = None,
        source: str = "manual",
    ) -> tuple[UserReference, bool]:
        if kind not in cls.KINDS:
            raise ReferenceError("Unsupported reference kind")
        safe_url = cls._safe_url(source_url)
        safe_hash = cls._safe_hash(file_hash)
        source_value = str(source or "manual").strip()[:64] or "manual"
        now = _utcnow()

        existing = await cls._find_existing(
            session,
            user_id=user_id,
            source_url=safe_url,
            kind=kind,
            file_hash=safe_hash,
        )
        if existing is not None:
            existing.kind = kind
            existing.status = "ready"
            existing.source_url = safe_url
            existing.last_used_at = now
            existing.source = source_value
            if safe_hash:
                existing.file_hash = safe_hash
            if label.strip():
                existing.label = label.strip()[:120]
            if original_filename:
                existing.original_filename = original_filename[:255]
            if content_type:
                existing.content_type = content_type[:255]
            await cls._prune_kind(session, user_id=user_id, kind=kind)
            await session.commit()
            return existing, True

        row = UserReference(
            user_id=user_id,
            kind=kind,
            status="ready",
            label=label.strip()[:120] or None,
            source_url=safe_url,
            file_hash=safe_hash,
            original_filename=(original_filename or "")[:255] or None,
            content_type=(content_type or "")[:255] or None,
            source=source_value,
            last_used_at=now,
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            replay = await cls._find_existing(
                session,
                user_id=user_id,
                source_url=safe_url,
                kind=kind,
                file_hash=safe_hash,
            )
            if replay is None:
                raise
            replay.status = "ready"
            replay.kind = kind
            replay.source_url = safe_url
            replay.last_used_at = now
            replay.source = source_value
            if safe_hash:
                replay.file_hash = safe_hash
            if label.strip():
                replay.label = label.strip()[:120]
            if original_filename:
                replay.original_filename = original_filename[:255]
            if content_type:
                replay.content_type = content_type[:255]
            await cls._prune_kind(session, user_id=user_id, kind=kind)
            await session.commit()
            return replay, True

        await cls._prune_kind(session, user_id=user_id, kind=kind)
        await session.commit()
        return row, False

    @classmethod
    async def list_owned(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        kind: str | None = None,
        limit: int = 100,
    ) -> list[UserReference]:
        stmt = select(UserReference).where(
            UserReference.user_id == user_id,
            UserReference.status == "ready",
        )
        if kind:
            if kind not in cls.KINDS:
                raise ReferenceError("Unsupported reference kind")
            stmt = stmt.where(UserReference.kind == kind)
        return list(
            (
                await session.scalars(
                    stmt.order_by(
                        UserReference.last_used_at.desc().nullslast(),
                        UserReference.created_at.desc(),
                        UserReference.id.desc(),
                    ).limit(max(1, min(limit, 100)))
                )
            ).all()
        )

    @staticmethod
    async def get_owned(
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        reference_id: uuid.UUID,
    ) -> UserReference:
        row = await session.get(UserReference, reference_id)
        if row is None or row.user_id != user_id or row.status != "ready":
            raise LookupError("Reference not found")
        return row

    @classmethod
    async def resolve_owned(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        reference_ids: list[uuid.UUID],
    ) -> list[UserReference]:
        rows: list[UserReference] = []
        for reference_id in dict.fromkeys(reference_ids):
            rows.append(
                await cls.get_owned(session, user_id=user_id, reference_id=reference_id)
            )
        return rows

    @classmethod
    async def touch_urls(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        source_urls: list[str],
    ) -> int:
        urls = list(dict.fromkeys(str(value or "").strip() for value in source_urls))
        urls = [value for value in urls if value]
        if not urls:
            return 0
        rows = list(
            (
                await session.scalars(
                    select(UserReference).where(
                        UserReference.user_id == user_id,
                        UserReference.status == "ready",
                        UserReference.source_url.in_(urls[:64]),
                    )
                )
            ).all()
        )
        if not rows:
            return 0
        now = _utcnow()
        touched_kinds: set[str] = set()
        for row in rows:
            row.last_used_at = now
            touched_kinds.add(row.kind)
        for kind in touched_kinds:
            await cls._prune_kind(session, user_id=user_id, kind=kind)
        await session.commit()
        return len(rows)

    @classmethod
    async def remove(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        reference_id: uuid.UUID,
    ) -> None:
        row = await cls.get_owned(session, user_id=user_id, reference_id=reference_id)
        row.status = "deleted"
        await session.commit()

    @staticmethod
    def public_view(row: UserReference) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "kind": row.kind,
            "label": row.label,
            "url": row.source_url,
            "filename": row.original_filename,
            "content_type": row.content_type,
            "source": row.source,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        }
