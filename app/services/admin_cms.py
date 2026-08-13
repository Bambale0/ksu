from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import CmsDocument, CmsDocumentVersion
from app.db.models import AdminAccount
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,158}[a-z0-9]$")


class AdminCmsService:
    @staticmethod
    async def list_documents(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        limit: int = 100,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "cms.read")
        rows = list(
            (
                await session.scalars(
                    select(CmsDocument)
                    .order_by(CmsDocument.updated_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            ).all()
        )
        return {
            "items": [
                {
                    "id": str(item.id),
                    "slug": item.slug,
                    "title": item.title,
                    "status": item.status,
                    "created_at": item.created_at.isoformat(),
                    "updated_at": item.updated_at.isoformat(),
                }
                for item in rows
            ]
        }

    @staticmethod
    async def get_document(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        document_id: uuid.UUID,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "cms.read")
        document = await session.get(CmsDocument, document_id)
        if document is None:
            raise LookupError("CMS document not found")
        versions = list(
            (
                await session.scalars(
                    select(CmsDocumentVersion)
                    .where(CmsDocumentVersion.document_id == document_id)
                    .order_by(CmsDocumentVersion.version.desc())
                )
            ).all()
        )
        return {
            "id": str(document.id),
            "slug": document.slug,
            "title": document.title,
            "status": document.status,
            "versions": [
                {
                    "id": str(item.id),
                    "version": item.version,
                    "title": item.title,
                    "body": item.body,
                    "status": item.status,
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "created_at": item.created_at.isoformat(),
                }
                for item in versions
            ],
        }

    @staticmethod
    async def save_document(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        slug: str,
        title: str,
        body: str,
        idempotency_key: str,
        request_id: str,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "cms.save", confirmed=True)
        normalized_slug = slug.strip().lower()
        clean_title = title.strip()
        clean_body = body.strip()
        if not _SLUG_RE.fullmatch(normalized_slug):
            raise ValueError("Invalid CMS slug")
        if not clean_title or len(clean_title) > 255:
            raise ValueError("Invalid CMS title")
        if not clean_body or len(clean_body) > 500_000:
            raise ValueError("Invalid CMS body")
        payload = {"slug": normalized_slug, "title": clean_title, "body": clean_body}

        async def operation() -> dict[str, Any]:
            document = await session.scalar(
                select(CmsDocument).where(CmsDocument.slug == normalized_slug).with_for_update()
            )
            if document is None:
                document = CmsDocument(slug=normalized_slug, title=clean_title, status="draft")
                session.add(document)
                await session.flush()
            else:
                document.title = clean_title
            latest = await session.scalar(
                select(CmsDocumentVersion)
                .where(CmsDocumentVersion.document_id == document.id)
                .order_by(CmsDocumentVersion.version.desc())
                .limit(1)
            )
            version_number = (latest.version if latest else 0) + 1
            version = CmsDocumentVersion(
                document_id=document.id,
                version=version_number,
                title=clean_title,
                body=clean_body,
                status="draft",
                created_by_admin_id=admin.id,
            )
            session.add(version)
            await session.flush()
            return {
                "document_id": str(document.id),
                "version_id": str(version.id),
                "version": version.version,
                "status": version.status,
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="cms.save",
            target_id=normalized_slug,
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def publish_document(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "cms.publish", confirmed=confirmed)
        payload = {"version_id": str(version_id) if version_id else None}

        async def operation() -> dict[str, Any]:
            document = await session.scalar(
                select(CmsDocument).where(CmsDocument.id == document_id).with_for_update()
            )
            if document is None:
                raise LookupError("CMS document not found")
            if version_id:
                version = await session.scalar(
                    select(CmsDocumentVersion)
                    .where(
                        CmsDocumentVersion.id == version_id,
                        CmsDocumentVersion.document_id == document_id,
                    )
                    .with_for_update()
                )
            else:
                version = await session.scalar(
                    select(CmsDocumentVersion)
                    .where(CmsDocumentVersion.document_id == document_id)
                    .order_by(CmsDocumentVersion.version.desc())
                    .with_for_update()
                    .limit(1)
                )
            if version is None:
                raise LookupError("CMS document version not found")
            published = list(
                (
                    await session.scalars(
                        select(CmsDocumentVersion)
                        .where(
                            CmsDocumentVersion.document_id == document_id,
                            CmsDocumentVersion.status == "published",
                        )
                        .with_for_update()
                    )
                ).all()
            )
            for old in published:
                old.status = "superseded"
            now = datetime.now(UTC)
            version.status = "published"
            version.published_by_admin_id = admin.id
            version.published_at = now
            document.status = "published"
            document.title = version.title
            return {
                "document_id": str(document.id),
                "version_id": str(version.id),
                "version": version.version,
                "status": version.status,
                "published_at": now.isoformat(),
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="cms.publish",
            target_id=str(document_id),
            request_payload=payload,
            operation=operation,
        )
