from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.action_context_models import GenerationActionContext
from app.db.models import Generation
from app.services import action_telemetry
from app.services.generation_actions import resolver_for
from app.services.generation_actions.base import ActionResolveError
from app.services.generation_actions.core import GenerationActionService

_EDIT_MODE = {
    "remix": "image_to_image",
    "edit": "image_to_image",
    "animate": "image_to_video",
    "repeat": None,  # resolved from the source media type
}

_EDIT_PRESETS = (
    {"id": "clothes", "label": "Одежда"},
    {"id": "hair", "label": "Причёска"},
    {"id": "hair_color", "label": "Цвет волос"},
    {"id": "nails", "label": "Ногти"},
    {"id": "background", "label": "Фон"},
    {"id": "style", "label": "Стиль"},
    {"id": "details", "label": "Детали"},
    {"id": "custom", "label": "Своё"},
)


class ActionContextError(ValueError):
    pass


class ActionContextDisabledError(ActionContextError):
    pass


class ActionContextNotFoundError(LookupError):
    pass


class ActionContextExpiredError(ActionContextError):
    pass


def action_target_mode(generation: Generation, action: str) -> str | None:
    canonical = GenerationActionService.canonical_action(action)
    mode = _EDIT_MODE.get(canonical)
    if mode is not None:
        return mode
    if canonical == "repeat":
        media_type = GenerationActionService.media_type(generation)
        return f"text_to_{media_type}"
    return None


def context_generation(generation: Generation) -> dict[str, object]:
    """Public, privacy-safe slice of the source generation for the Mini App."""
    params = generation.parameters or {}
    model_id = GenerationActionService.model_id(generation)
    model_title = str(params.get("_model_title") or model_id or "ROXY")
    prompt_hidden = generation.action_type == "trend"
    return {
        "id": str(generation.id),
        "status": generation.status,
        "media_type": GenerationActionService.media_type(generation),
        "result_url": GenerationActionService.result_url(generation),
        "model_id": model_id,
        "model_title": model_title,
        "prompt": "" if prompt_hidden else generation.prompt,
        "prompt_hidden": prompt_hidden,
        "parent_generation_id": str(generation.parent_generation_id) if generation.parent_generation_id else None,
        "action_type": generation.action_type,
        "publication_scope": generation.publication_scope,
    }


def action_defaults(
    generation: Generation,
    action: str,
    default_model_id: str | None,
) -> dict[str, object]:
    if not default_model_id:
        return {
            "model_id": None,
            "prompt": "",
            "parameters": {},
            "billing_seconds": None,
            "input_url": None,
        }

    canonical = GenerationActionService.canonical_action(action)
    params = dict(generation.parameters or {})
    prompt = "" if generation.action_type == "trend" else generation.prompt
    reusable = GenerationActionService.reusable_parameters(generation, default_model_id)
    input_url: str | None = generation.input_url

    if canonical in {"remix", "edit", "animate"}:
        reusable = {}
        input_url = GenerationActionService.result_url(generation)
        prompt = ""
    elif action == "new_prompt":
        prompt = ""

    return {
        "model_id": default_model_id,
        "prompt": prompt,
        "parameters": reusable,
        "billing_seconds": params.get("_billing_seconds"),
        "input_url": input_url,
    }


def edit_presets() -> list[dict[str, str]]:
    return [dict(item) for item in _EDIT_PRESETS]


def build_action_context_payload(generation: Generation, action: str) -> dict[str, object]:
    """Build the exact restore payload served by the action-context endpoints.

    ``GET /generations/{id}/action-context?action=`` resolves this on demand and
    ``create_action_context`` snapshots it into a durable row so the same screen
    can be restored later from a short ``action_context_id``.
    """
    if not GenerationActionService.action_allowed(generation, action):
        raise ActionContextError(f"Action '{action}' is not available for this generation")

    available = GenerationActionService.available_actions(generation)
    action_spec = next(item for item in available if item.id == action)
    default_model_id = (
        None
        if action == "publish"
        else GenerationActionService.default_model_id(generation, action)
    )
    candidates = (
        []
        if action == "publish"
        else GenerationActionService.public_candidates(generation, action)
    )
    images, videos = GenerationActionService.parent_references(generation)

    payload: dict[str, object] = {
        "generation": context_generation(generation),
        "action": action_spec.public_dict(),
        "candidate_models": candidates,
        "defaults": action_defaults(generation, action, default_model_id),
        "source_url": GenerationActionService.result_url(generation),
        "source_references": {"images": images, "videos": videos},
        "edit_presets": edit_presets() if action == "edit" else [],
    }

    # Scenario-specific resolver output (mode/source media/quote hints) is
    # merged without touching the keys above, so the Mini App contract is
    # purely additive.
    resolver = resolver_for(action)
    if resolver is not None:
        try:
            payload["scenario"] = resolver.resolve(generation)
        except ActionResolveError:
            payload["scenario"] = None
    return payload


async def create_action_context(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    generation: Generation,
    action: str,
    ttl_seconds: int | None = None,
) -> GenerationActionContext:
    """Create (or reuse the active row for) a server-owned action context.

    The partial unique index guarantees at most one active context per user,
    source generation and action. Conflict resolution returns the existing row,
    so delivery/worker retries never pile up duplicate snapshot rows.
    """
    if not settings.generation_action_contexts_enabled:
        raise ActionContextDisabledError("Generation action contexts are disabled")

    canonical = GenerationActionService.canonical_action(action)
    payload = build_action_context_payload(generation, action)
    ttl = ttl_seconds or settings.generation_action_context_ttl_seconds
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=max(60, ttl))
    values = {
        "user_id": user_id,
        "source_generation_id": generation.id,
        "action": canonical,
        "target_mode": action_target_mode(generation, canonical),
        "target_model_id": payload.get("defaults", {}).get("model_id"),
        "payload_json": payload,
        "status": "active",
        "expires_at": expires_at,
        "created_at": now,
        "updated_at": now,
    }
    stmt = pg_insert(GenerationActionContext).values(**values)
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["user_id", "source_generation_id", "action"],
        index_where=text("status = 'active'"),
    )
    await session.execute(stmt)
    existing = await session.scalar(
        select(GenerationActionContext).where(
            GenerationActionContext.user_id == user_id,
            GenerationActionContext.source_generation_id == generation.id,
            GenerationActionContext.action == canonical,
            GenerationActionContext.status == "active",
        )
    )
    if existing is None:
        raise ActionContextError("Failed to create generation action context")
    action_telemetry.track(
        action_telemetry.ACTION_CONTEXT_CREATED,
        user_id=user_id,
        context_id=str(existing.id),
        action=canonical,
        generation_id=str(generation.id),
    )
    return existing


async def get_action_context(
    session: AsyncSession,
    context_id: uuid.UUID,
    user_id: uuid.UUID,
) -> GenerationActionContext:
    """Resolve an owner-scoped, non-expired action context and count the open."""
    context = await session.get(GenerationActionContext, context_id)
    if context is None or context.user_id != user_id:
        # Do not leak the existence of rows that belong to another user.
        raise ActionContextNotFoundError("Generation action context not found")
    if context.expires_at is not None and context.expires_at <= datetime.now(UTC):
        raise ActionContextExpiredError("Generation action context has expired")
    context.opened_count = (context.opened_count or 0) + 1
    context.opened_at = datetime.now(UTC)
    action_telemetry.track(
        action_telemetry.ACTION_CONTEXT_OPENED,
        user_id=user_id,
        context_id=str(context.id),
        action=context.action,
        generation_id=str(context.source_generation_id),
    )
    return context


async def mark_action_context_executed(
    session: AsyncSession,
    context_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Idempotently mark an owner-scoped context as executed."""
    context = await session.get(GenerationActionContext, context_id)
    if context is None or context.user_id != user_id:
        return False
    if context.status == "active":
        context.status = "executed"
        context.executed_at = datetime.now(UTC)
        action_telemetry.track(
            action_telemetry.ACTION_EXECUTED,
            user_id=user_id,
            context_id=str(context.id),
            action=context.action,
            generation_id=str(context.source_generation_id),
        )
        return True
    return False