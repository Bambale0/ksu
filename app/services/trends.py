from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.admin_models import AdminTrend
from app.db.models import Generation
from app.services.credits import InternalCreditService
from app.services.generations import GenerationService
from app.services.model_catalog import ModelCatalog, ModelSpec

logger = logging.getLogger(__name__)

_REFERENCE_LIST_FIELDS = (
    "reference_image_urls",
    "image_input",
    "image_urls",
    "input_urls",
)
_REFERENCE_SINGLE_FIELDS = (
    "image_url",
    "first_frame_url",
    "first_frame",
)


class TrendRecipeError(ValueError):
    pass


class TrendService:
    """Server-owned curated trend templates and one-tap generation orchestration."""

    @staticmethod
    def normalize_recipe(title: str, payload: dict[str, Any]) -> dict[str, Any]:
        clean_title = str(title or "").strip()
        if not clean_title or len(clean_title) > 80:
            raise TrendRecipeError("Trend title must contain 1..80 characters")

        description = str(payload.get("description") or "").strip()
        if len(description) > 240:
            raise TrendRecipeError("Trend description must be at most 240 characters")

        model_id = str(payload.get("model_id") or payload.get("model") or "").strip()
        if not model_id:
            raise TrendRecipeError("model_id is required")
        spec = ModelCatalog.get(model_id)

        prompt = str(payload.get("prompt") or payload.get("prompt_text") or "").strip()
        if not prompt or len(prompt) > 8000:
            raise TrendRecipeError("Hidden trend prompt must contain 1..8000 characters")

        preview_url = TrendService._safe_http_url(payload.get("preview_url"), field="preview_url")
        media_type = str(payload.get("media_type") or spec.media_type).strip().lower()
        if media_type not in {"image", "video"} or media_type != spec.media_type:
            raise TrendRecipeError("media_type must match the selected model")

        parameters = payload.get("parameters")
        if parameters is None:
            parameters = payload.get("generation_settings") or {}
        if not isinstance(parameters, dict):
            raise TrendRecipeError("parameters must be an object")
        parameters = dict(parameters)
        for key in ("model", "model_id", "kind", "user_input", "count"):
            parameters.pop(key, None)

        raw_input_mode = payload.get("input_mode") or payload.get("user_input") or "none"
        input_mode = str(raw_input_mode).strip().lower()
        if input_mode in {"photo", "image", "reference", "references"}:
            input_mode = "image"
        elif input_mode in {"none", "text", "prompt"}:
            input_mode = "none"
        else:
            raise TrendRecipeError("input_mode must be 'none' or 'image'")

        reference_field = TrendService._reference_field(spec)
        default_max = 1 if reference_field in _REFERENCE_SINGLE_FIELDS else 8
        min_references = int(payload.get("min_references", 1 if input_mode == "image" else 0))
        max_references = int(
            payload.get("max_references", default_max if input_mode == "image" else 0)
        )
        if min_references < 0 or max_references < min_references or max_references > 16:
            raise TrendRecipeError("Reference limits are invalid")
        if input_mode == "none" and (min_references or max_references):
            raise TrendRecipeError("Reference limits require input_mode='image'")
        if input_mode == "image" and reference_field is None:
            raise TrendRecipeError("Selected model does not accept image references")
        if reference_field in _REFERENCE_SINGLE_FIELDS and max_references > 1:
            raise TrendRecipeError("Selected model accepts only one reference image")

        billing_seconds_raw = payload.get("billing_seconds")
        if billing_seconds_raw is None and spec.duration_field:
            billing_seconds_raw = parameters.get(spec.duration_field)
        billing_seconds = int(billing_seconds_raw) if billing_seconds_raw not in (None, "") else None
        if billing_seconds is not None and billing_seconds <= 0:
            raise TrendRecipeError("billing_seconds must be positive")

        tags = payload.get("tags") or []
        if not isinstance(tags, list):
            raise TrendRecipeError("tags must be an array")
        clean_tags = []
        for item in tags[:20]:
            value = str(item).strip().lower()
            if value and len(value) <= 40 and value not in clean_tags:
                clean_tags.append(value)

        sort_order = int(payload.get("sort_order", 0))
        if sort_order < -100_000 or sort_order > 100_000:
            raise TrendRecipeError("sort_order is out of range")
        usage_count = max(0, int(payload.get("usage_count", 0)))

        return {
            "schema_version": 1,
            "description": description,
            "media_type": media_type,
            "preview_url": preview_url,
            "model_id": spec.id,
            "prompt": prompt,
            "parameters": parameters,
            "billing_seconds": billing_seconds,
            "input_mode": input_mode,
            "min_references": min_references,
            "max_references": max_references,
            "tags": clean_tags,
            "sort_order": sort_order,
            "usage_count": usage_count,
        }

    @staticmethod
    async def validate_recipe(
        session: AsyncSession,
        *,
        title: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        recipe = TrendService.normalize_recipe(title, payload)
        refs = ["https://example.invalid/trend-reference.jpg"] * recipe["min_references"]
        parameters = TrendService._parameters_with_references(recipe, refs)
        try:
            await GenerationService.prepare_request(
                session,
                model_id=recipe["model_id"],
                prompt=recipe["prompt"],
                parameters=parameters,
                billing_seconds=recipe["billing_seconds"],
            )
        except ValueError as exc:
            raise TrendRecipeError(f"Trend generation recipe is invalid: {exc}") from exc
        return recipe

    @staticmethod
    def admin_view(item: AdminTrend) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "title": item.title,
            "payload": item.payload,
            "is_active": item.is_active,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }

    @staticmethod
    async def list_public(
        session: AsyncSession,
        *,
        limit: int = 50,
        media_type: str | None = None,
    ) -> dict[str, Any]:
        rows = list(
            (
                await session.scalars(
                    select(AdminTrend)
                    .where(AdminTrend.is_active.is_(True))
                    .order_by(AdminTrend.created_at.desc())
                    .limit(max(1, min(limit, 100)))
                )
            ).all()
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            try:
                view = await TrendService.public_view(session, row)
            except (ValueError, KeyError):
                continue
            if media_type and view["media_type"] != media_type:
                continue
            items.append(view)
        items.sort(
            key=lambda item: (int(item["sort_order"]), item["created_at"]),
            reverse=True,
        )
        return {"items": items}

    @staticmethod
    async def get_public(session: AsyncSession, *, trend_id: uuid.UUID) -> dict[str, Any]:
        item = await session.get(AdminTrend, trend_id)
        if item is None or not item.is_active:
            raise LookupError("Trend not found")
        try:
            return await TrendService.public_view(session, item)
        except (ValueError, KeyError) as exc:
            raise LookupError("Trend not found") from exc

    @staticmethod
    async def public_view(session: AsyncSession, item: AdminTrend) -> dict[str, Any]:
        recipe = TrendService.normalize_recipe(item.title, item.payload or {})
        refs = ["https://example.invalid/trend-reference.jpg"] * recipe["min_references"]
        parameters = TrendService._parameters_with_references(recipe, refs)
        spec, _clean, cost, seconds, _unit = await GenerationService.prepare_request(
            session,
            model_id=recipe["model_id"],
            prompt=recipe["prompt"],
            parameters=parameters,
            billing_seconds=recipe["billing_seconds"],
        )
        return {
            "id": str(item.id),
            "title": item.title,
            "description": recipe["description"],
            "media_type": recipe["media_type"],
            "preview_url": recipe["preview_url"],
            "model": {
                "id": spec.id,
                "title": spec.title,
                "family": spec.family,
            },
            "cost_credits": TrendService._amount(cost),
            "cost_rub": TrendService._amount(InternalCreditService.rubles_for(cost)),
            "billing_seconds": seconds,
            "reference_requirements": {
                "kind": recipe["input_mode"],
                "min": recipe["min_references"],
                "max": recipe["max_references"],
            },
            "tags": recipe["tags"],
            "usage_count": recipe["usage_count"],
            "sort_order": recipe["sort_order"],
            "prompt_hidden": True,
            "prompt_actions_allowed": False,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    async def run(
        session: AsyncSession,
        redis: Redis,
        *,
        user_id: uuid.UUID,
        trend_id: uuid.UUID,
        reference_urls: list[str],
    ) -> tuple[Generation, dict[str, Any]]:
        item = await session.get(AdminTrend, trend_id)
        if item is None or not item.is_active:
            raise LookupError("Trend not found")
        recipe = TrendService.normalize_recipe(item.title, item.payload or {})
        refs = [TrendService._safe_http_url(url, field="reference_url") for url in reference_urls]
        if len(refs) < recipe["min_references"] or len(refs) > recipe["max_references"]:
            raise TrendRecipeError(
                f"Trend requires {recipe['min_references']}..{recipe['max_references']} reference images"
            )
        if recipe["input_mode"] == "none" and refs:
            raise TrendRecipeError("This trend does not accept reference images")

        parameters = TrendService._parameters_with_references(recipe, refs)
        generation = await GenerationService.create(
            session,
            redis,
            user_id=user_id,
            model_id=recipe["model_id"],
            prompt=recipe["prompt"],
            parameters=parameters,
            billing_seconds=recipe["billing_seconds"],
            action_type="trend",
        )

        # Usage is analytics only. GenerationService has already committed the financially
        # authoritative generation/debit/outbox transaction, so analytics must never turn
        # a successful charge and task creation into an HTTP 500.
        try:
            locked = await session.scalar(
                select(AdminTrend).where(AdminTrend.id == trend_id).with_for_update()
            )
            if locked is not None:
                payload = dict(locked.payload or {})
                payload["usage_count"] = max(0, int(payload.get("usage_count", 0))) + 1
                locked.payload = payload
                await session.commit()
        except Exception:
            await session.rollback()
            logger.warning("Trend usage analytics failed for %s", trend_id, exc_info=True)

        return generation, {
            "trend_id": str(trend_id),
            "prompt_hidden": True,
            "prompt_actions_allowed": False,
            "model": {
                "id": recipe["model_id"],
                "title": ModelCatalog.get(recipe["model_id"]).title,
            },
        }

    @staticmethod
    def _parameters_with_references(
        recipe: dict[str, Any],
        reference_urls: list[str],
    ) -> dict[str, Any]:
        parameters = dict(recipe.get("parameters") or {})
        spec = ModelCatalog.get(str(recipe["model_id"]))
        for field in (*_REFERENCE_LIST_FIELDS, *_REFERENCE_SINGLE_FIELDS):
            parameters.pop(field, None)
        if not reference_urls:
            return parameters
        field = TrendService._reference_field(spec)
        if field is None:
            raise TrendRecipeError("Selected model does not accept image references")
        if field in _REFERENCE_SINGLE_FIELDS and len(reference_urls) != 1:
            raise TrendRecipeError("Selected model requires exactly one reference image")
        parameters[field] = reference_urls if field in _REFERENCE_LIST_FIELDS else reference_urls[0]
        return parameters

    @staticmethod
    def _reference_field(spec: ModelSpec) -> str | None:
        known = set(spec.known_fields)
        for field in (*_REFERENCE_LIST_FIELDS, *_REFERENCE_SINGLE_FIELDS):
            if field in known:
                return field
        return None

    @staticmethod
    def _safe_http_url(value: Any, *, field: str) -> str:
        url = str(value or "").strip()
        if not url or len(url) > 4000:
            raise TrendRecipeError(f"{field} must be a valid HTTP(S) URL")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise TrendRecipeError(f"{field} must be a valid HTTP(S) URL")
        return url

    @staticmethod
    def _amount(value: Decimal | str | int | float) -> str:
        return format(Decimal(str(value)), ".2f")
