from __future__ import annotations

import logging
import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminTrend
from app.db.models import Generation
from app.services.generations import GenerationService
from app.services.model_catalog import ModelCatalog
from app.services.pinterest_flow_contract import (
    PinterestFlowError,
    build_pinterest_prompt,
    is_pinterest_trend,
    validate_pinterest_flow,
)
from app.services.trends import TrendRecipeError, TrendService

logger = logging.getLogger(__name__)


class PinterestFlowService:
    """Dedicated server-owned Pinterest repeat flow.

    Pinterest recipes are deliberately kept out of generic Trends. Image roles,
    anthropometrics and consent are enforced here before the normal generation
    pipeline performs model validation, billing, persistence and provider enqueue.
    """

    @staticmethod
    async def list_public(
        session: AsyncSession,
        *,
        limit: int = 50,
    ) -> dict[str, Any]:
        return await TrendService.list_public(session, limit=limit, pinterest_only=True)

    @staticmethod
    async def get_public(session: AsyncSession, *, trend_id: uuid.UUID) -> dict[str, Any]:
        item = await TrendService.get_public(session, trend_id=trend_id, allow_pinterest=True)
        raw = await session.get(AdminTrend, trend_id)
        if raw is None or not is_pinterest_trend(raw.title, raw.payload or {}):
            raise LookupError("Pinterest service not found")
        return item

    @staticmethod
    async def run(
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        trend_id: uuid.UUID,
        reference_urls: list[str],
        height_cm: int,
        weight_kg: int,
        confirmed: bool,
    ) -> tuple[Generation, dict[str, Any]]:
        item = await session.get(AdminTrend, trend_id)
        if item is None or not item.is_active or not is_pinterest_trend(item.title, item.payload or {}):
            raise LookupError("Pinterest service not found")

        recipe = TrendService.normalize_recipe(item.title, item.payload or {})
        refs = validate_pinterest_flow(
            reference_urls=reference_urls,
            height_cm=height_cm,
            weight_kg=weight_kg,
            confirmed=confirmed,
        )
        refs = [TrendService._safe_http_url(url, field="reference_url") for url in refs]

        if recipe["media_type"] != "image":
            raise PinterestFlowError("Pinterest Flow currently requires an image generation model")
        if recipe["input_mode"] != "image":
            raise PinterestFlowError("Pinterest Flow recipe must accept image references")

        prompt = build_pinterest_prompt(
            recipe["prompt"],
            height_cm=height_cm,
            weight_kg=weight_kg,
            reference_count=len(refs),
        )
        parameters = TrendService._parameters_with_references(recipe, refs)
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user_id,
            model_id=recipe["model_id"],
            prompt=prompt,
            parameters=parameters,
            billing_seconds=recipe["billing_seconds"],
            action_type="pinterest_flow",
        )

        try:
            locked = await session.scalar(select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update())
            if locked is not None:
                payload = dict(locked.payload or {})
                payload["usage_count"] = max(0, int(payload.get("usage_count", 0))) + 1
                locked.payload = payload
                await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("Pinterest Flow usage analytics failed for %s", trend_id, exc_info=True)

        return generation, {
            "service": "pinterest",
            "trend_id": str(trend_id),
            "prompt_hidden": True,
            "prompt_actions_allowed": False,
            "reference_roles": {
                "scene": 1,
                "identity": 2,
                "supporting_identity": max(0, len(refs) - 2),
            },
            "model": {"id": recipe["model_id"], "title": ModelCatalog.get(recipe["model_id"]).title},
        }


__all__ = ["PinterestFlowError", "PinterestFlowService", "TrendRecipeError"]
