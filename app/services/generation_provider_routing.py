from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Generation

_PROVIDER_ROUTES: dict[str, tuple[str, ...]] = {
    "seedance-2.0": ("neironych", "kie"),
    "seedance-2.5": ("neironych", "kie"),
    "nano-banana-pro": ("neironych", "nexus"),
}


def route_for_model(model_id: str) -> tuple[str, ...] | None:
    return _PROVIDER_ROUTES.get(str(model_id or "").strip().lower())


def route_snapshot(parameters: dict[str, Any] | None) -> tuple[str, ...]:
    raw = (parameters or {}).get("_provider_route")
    if not isinstance(raw, list):
        return ()
    return tuple(str(item).strip().lower() for item in raw if str(item).strip())


def route_index(generation: Generation) -> int:
    params = generation.parameters or {}
    try:
        value = int(params.get("_provider_route_index") or 0)
    except (TypeError, ValueError):
        value = 0
    return max(0, value)


def idempotency_key(generation: Generation) -> str:
    return f"generation:{generation.id}:provider:{route_index(generation)}"


async def switch_to_fallback(
    session: AsyncSession,
    generation_id: uuid.UUID,
    *,
    reason: str,
    expected_provider: str | None = None,
    terminal_failure: bool = False,
) -> Generation | None:
    generation = await session.scalar(
        select(Generation).where(Generation.id == generation_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    if generation is None or generation.status in {"succeeded", "failed"}:
        return None

    if expected_provider is not None and generation.provider != expected_provider:
        return None
    if not terminal_failure and (
        generation.external_id or (generation.parameters or {}).get("_submission_uncertain")
    ):
        return None

    route = route_snapshot(generation.parameters)
    if not route:
        return None

    current_provider = str(generation.provider or "").strip().lower()
    index = route_index(generation)
    if index >= len(route) or route[index] != current_provider:
        try:
            index = route.index(current_provider)
        except ValueError:
            return None

    next_index = index + 1
    if next_index >= len(route):
        return None

    params = dict(generation.parameters or {})
    history = list(params.get("_provider_attempts") or [])
    history.append(
        {
            "ordinal": index,
            "provider": current_provider,
            "outcome": "fallback",
            "reason": str(reason or "")[:500],
            "external_id": generation.external_id,
            "idempotency_key": idempotency_key(generation),
            "at": datetime.now(UTC).isoformat(),
        }
    )
    params["_provider_attempts"] = history[-8:]
    params["_provider_route_index"] = next_index
    params.pop("_submission_uncertain", None)
    params.pop("_submission_uncertain_at", None)
    params.pop("_provider_submitted_at", None)

    generation.parameters = params
    generation.provider = route[next_index]
    generation.external_id = None
    generation.status = "retry"
    generation.error = f"Fallback from {current_provider}: {reason}"[:4000]
    await session.commit()
    return generation
