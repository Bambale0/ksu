from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reference_models import UserReference


class ReferenceError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ReferenceService:
    KINDS = {"image", "video", "audio"}

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
    ) -> tuple[UserReference, bool]:
        if kind not in cls.KINDS:
            raise ReferenceError("Unsupported reference kind")
        safe_url = cls._safe_url(source_url)
        existing = await session.scalar(
            select(UserReference).where(
                UserReference.user_id == user_id,
                UserReference.source_url == safe_url,
            )
        )
        if existing is not None:
            existing.status = "ready"
            existing.last_used_at = _utcnow()
            if label.strip():
                existing.label = label.strip()[:120]
            await session.commit()
            return existing, True

        row = UserReference(
            user_id=user_id,
            kind=kind,
            status="ready",
            label=label.strip()[:120] or None,
            source_url=safe_url,
            original_filename=(original_filename or "")[:255] or None,
            content_type=(content_type or "")[:255] or None,
            last_used_at=_utcnow(),
        )
        session.add(row)
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
                    stmt.order_by(UserReference.last_used_at.desc(), UserReference.created_at.desc())
                    .limit(max(1, min(limit, 100)))
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
            "created_at": row.created_at.isoformat(),
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        }
