from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_content_models import GenerationModerationState
from app.db.admin_models import AdminTrend, PromptLibraryItem
from app.db.models import AdminAccount, Generation
from app.services.admin_commands import AdminCommandLedger
from app.services.admin_policy import AdminPolicy
from app.services.trends import TrendService

PromptModerationAction = Literal["approve", "reject", "deactivate"]
FeedModerationAction = Literal["visible", "blurred", "removed"]


class AdminContentService:
    @staticmethod
    async def list_prompts(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "prompts.read")
        stmt = select(PromptLibraryItem)
        if status:
            stmt = stmt.where(PromptLibraryItem.status == status)
        rows = list(
            (
                await session.scalars(
                    stmt.order_by(PromptLibraryItem.created_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            ).all()
        )
        return {"items": [AdminContentService._prompt_view(item) for item in rows]}

    @staticmethod
    def _prompt_view(item: PromptLibraryItem) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "title": item.title,
            "prompt": item.prompt,
            "status": item.status,
            "is_active": item.is_active,
            "created_by_user_id": str(item.created_by_user_id) if item.created_by_user_id else None,
            "moderated_by_admin_id": (
                str(item.moderated_by_admin_id) if item.moderated_by_admin_id else None
            ),
            "moderation_reason": item.moderation_reason,
            "moderated_at": item.moderated_at.isoformat() if item.moderated_at else None,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    async def get_prompt(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        prompt_id: uuid.UUID,
    ) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "prompts.read")
        item = await session.get(PromptLibraryItem, prompt_id)
        if item is None:
            raise LookupError("Prompt library item not found")
        return AdminContentService._prompt_view(item)

    @staticmethod
    async def moderate_prompt(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        prompt_id: uuid.UUID,
        action: PromptModerationAction,
        reason: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "prompts.moderate", confirmed=confirmed)
        clean_reason = reason.strip()
        if len(clean_reason) < 3 or len(clean_reason) > 1000:
            raise ValueError("Moderation reason must contain 3..1000 characters")
        payload = {"action": action, "reason": clean_reason}

        async def operation() -> dict[str, Any]:
            item = await session.scalar(
                select(PromptLibraryItem)
                .where(PromptLibraryItem.id == prompt_id)
                .with_for_update()
            )
            if item is None:
                raise LookupError("Prompt library item not found")
            if action == "approve":
                item.status = "approved"
                item.is_active = True
            elif action == "reject":
                item.status = "rejected"
                item.is_active = False
            else:
                item.status = "deactivated"
                item.is_active = False
            item.moderated_by_admin_id = admin.id
            item.moderation_reason = clean_reason
            item.moderated_at = datetime.now(UTC)
            await session.flush()
            return AdminContentService._prompt_view(item)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="prompts.moderate",
            target_id=str(prompt_id),
            request_payload=payload,
            operation=operation,
        )

    @staticmethod
    async def list_trends(session: AsyncSession, *, admin: AdminAccount) -> dict[str, Any]:
        AdminPolicy.require_permission(admin, "social.moderate")
        rows = list(
            (
                await session.scalars(
                    select(AdminTrend).order_by(AdminTrend.created_at.desc()).limit(200)
                )
            ).all()
        )
        return {"items": [TrendService.admin_view(item) for item in rows]}

    @staticmethod
    async def create_trend(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        title: str,
        payload: dict[str, Any],
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "social.moderate", confirmed=confirmed)
        clean_title = title.strip()
        recipe = await TrendService.validate_recipe(
            session,
            title=clean_title,
            payload=payload,
        )
        command_payload = {"title": clean_title, "payload": recipe}

        async def operation() -> dict[str, Any]:
            item = AdminTrend(
                title=clean_title,
                payload=recipe,
                is_active=True,
                created_by_admin_id=admin.id,
            )
            session.add(item)
            await session.flush()
            return TrendService.admin_view(item)

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="social.moderate",
            target_id=None,
            request_payload=command_payload,
            operation=operation,
        )

    @staticmethod
    async def remove_trend(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        trend_id: uuid.UUID,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "social.moderate", confirmed=confirmed)

        async def operation() -> dict[str, Any]:
            item = await session.scalar(
                select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update()
            )
            if item is None:
                raise LookupError("Trend not found")
            item.is_active = False
            return {"id": str(item.id), "is_active": item.is_active}

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="social.moderate",
            target_id=str(trend_id),
            request_payload={"is_active": False},
            operation=operation,
        )

    @staticmethod
    async def moderate_generation(
        session: AsyncSession,
        *,
        admin: AdminAccount,
        generation_id: uuid.UUID,
        state: FeedModerationAction,
        reason: str,
        idempotency_key: str,
        request_id: str,
        confirmed: bool,
    ) -> tuple[dict[str, Any], bool]:
        AdminPolicy.authorize_action(admin, "social.moderate", confirmed=confirmed)
        clean_reason = reason.strip()
        if len(clean_reason) < 3 or len(clean_reason) > 1000:
            raise ValueError("Moderation reason must contain 3..1000 characters")
        payload = {"state": state, "reason": clean_reason}

        async def operation() -> dict[str, Any]:
            generation = await session.get(Generation, generation_id)
            if generation is None:
                raise LookupError("Generation not found")
            item = await session.get(GenerationModerationState, generation_id)
            if item is None:
                item = GenerationModerationState(
                    generation_id=generation_id,
                    state=state,
                    reason=clean_reason,
                    moderated_by_admin_id=admin.id,
                    moderated_at=datetime.now(UTC),
                )
                session.add(item)
            else:
                item.state = state
                item.reason = clean_reason
                item.moderated_by_admin_id = admin.id
                item.moderated_at = datetime.now(UTC)
            await session.flush()
            return {
                "generation_id": str(generation_id),
                "state": item.state,
                "reason": item.reason,
            }

        return await AdminCommandLedger.execute(
            session,
            idempotency_key=idempotency_key,
            admin_user_id=admin.id,
            request_id=request_id,
            action="social.moderate",
            target_id=str(generation_id),
            request_payload=payload,
            operation=operation,
        )
