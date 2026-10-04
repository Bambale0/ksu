from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Generation
from app.db.admin_models import AdminRuntimeSetting

_PROVIDER_ROUTES: dict[str, tuple[str, ...]] = {
    "nano-banana": ("nexus", "kie"),
    "nano-banana-edit": ("nexus", "kie"),
    "nano-banana-pro": ("nexus", "neironych", "kie"),
    "nano-banana-2": ("nexus", "kie"),
    "nano-banana-2-lite": ("nexus", "kie"),
    "gpt-image-2-t2i": ("nexus", "kie"),
    "gpt-image-2-i2i": ("nexus", "kie"),
    "seedream-5-lite-t2i": ("nexus", "kie"),
    "seedream-5-lite-i2i": ("nexus", "kie"),
    "seedream-5-pro-t2i": ("nexus", "kie"),
    "seedream-5-pro-i2i": ("nexus", "kie"),
    "seedance-2.0": ("nexus", "neironych", "kie"),
    "seedance-2.0-fast": ("nexus", "kie"),
    "seedance-2.0-mini": ("nexus", "kie"),
    "seedance-2.5": ("nexus", "neironych", "kie"),
    "wan-2.7-t2v": ("nexus", "kie"),
    "wan-2.7-i2v": ("nexus", "kie"),
    "kling-3.0": ("nexus", "kie"),
    "kling-motion-2.6": ("nexus", "kie"),
    "veo-3.1": ("nexus", "kie"),
    "gemini-omni-video": ("nexus", "kie"),
}

ROUTES_SETTING_KEY = "generation_provider_routes"


def route_options() -> dict[str, list[list[str]]]:
    options: dict[str, list[list[str]]] = {}
    for model, route in _PROVIDER_ROUTES.items():
        choices: list[list[str]] = [list(route)]
        for provider in route:
            choice = [provider]
            if choice not in choices:
                choices.append(choice)
        if len(route) > 2:
            for start in range(len(route)):
                choice = list(route[start:])
                if len(choice) > 1 and choice not in choices:
                    choices.append(choice)
            for fallback in route[1:]:
                choice = [route[0], fallback]
                if choice not in choices:
                    choices.append(choice)
        options[model] = choices
    return options


def validate_routes(routes: dict[str, Any]) -> dict[str, list[str]]:
    if set(routes) != set(_PROVIDER_ROUTES):
        raise ValueError("Specify routes for every managed generation model")
    validated: dict[str, list[str]] = {}
    for model in _PROVIDER_ROUTES:
        route = routes[model]
        allowed = route_options()[model]
        if route not in allowed:
            raise ValueError(f"Unsupported provider route for {model}")
        validated[model] = list(route)
    return validated


async def configured_routes(session: AsyncSession) -> dict[str, Any]:
    row = await session.get(AdminRuntimeSetting, ROUTES_SETTING_KEY, populate_existing=True)
    defaults = {k: list(v) for k, v in _PROVIDER_ROUTES.items()}
    if row is None:
        return {"revision": 1, "routes": defaults}
    stored_routes = row.value.get("routes") if isinstance(row.value, dict) else None
    # A route registry expansion is an explicit provider migration. Old rows
    # must not pin the three legacy Neironych routes forever or make reads fail.
    if not isinstance(stored_routes, dict) or set(stored_routes) != set(_PROVIDER_ROUTES):
        return {"revision": int(row.value.get("revision", 1)), "routes": defaults}
    return {"revision": int(row.value["revision"]), "routes": validate_routes(stored_routes)}


async def configured_route(session: AsyncSession, model: str) -> tuple[tuple[str, ...] | None, int]:
    if model not in _PROVIDER_ROUTES:
        return None, 0
    config = await configured_routes(session)
    return tuple(config["routes"][model]), config["revision"]


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
    params.pop("_neironych_submission", None)
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
