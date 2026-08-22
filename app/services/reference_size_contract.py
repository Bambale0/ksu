from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.reference_models import UserReference
from app.services.model_catalog import InvalidModelParametersError, ModelSpec
from app.services.model_ui_contract import build_public_model_ui_schema


def _field_urls(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            result.extend(_field_urls(item))
        return result
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            if key in {"url", "source_url", "image_url", "video_url", "audio_url"} or key.endswith("_url") or key.endswith("_urls"):
                result.extend(_field_urls(item))
        return result
    return []


def _request_user_id(session: AsyncSession, explicit: uuid.UUID | None) -> uuid.UUID | None:
    if explicit is not None:
        return explicit
    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return None
    value = info.get("current_user_id")
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


async def validate_reference_sizes(
    session: AsyncSession,
    *,
    spec: ModelSpec,
    parameters: dict[str, Any],
    user_id: uuid.UUID | None = None,
) -> None:
    """Enforce known model upload limits for the authenticated reference owner.

    Product-owned uploads have measured sizes. The user id is either passed by the
    create boundary or inherited from the authenticated request session. Public
    catalog/trend rendering and anonymous quotes never search another user's
    reference library by URL. Manual URLs have no trusted byte metadata and remain
    subject to provider/model-specific validation.
    """

    owner_id = _request_user_id(session, user_id)
    if owner_id is None:
        return

    schema = build_public_model_ui_schema(spec.public_dict())
    limits_by_url: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for field in schema.get("fields", []):
        if not isinstance(field, dict):
            continue
        max_size_mb = field.get("max_size_mb")
        name = str(field.get("name") or "")
        if not name or not isinstance(max_size_mb, int) or max_size_mb <= 0:
            continue
        for url in _field_urls(parameters.get(name)):
            limits_by_url[url].append((name, max_size_mb))

    if not limits_by_url:
        return

    rows = list(
        (
            await session.scalars(
                select(UserReference).where(
                    UserReference.user_id == owner_id,
                    UserReference.status == "ready",
                    UserReference.source_url.in_(list(limits_by_url)),
                )
            )
        ).all()
    )
    for row in rows:
        if row.size_bytes is None:
            continue
        for field_name, max_size_mb in limits_by_url.get(row.source_url, []):
            if row.size_bytes > max_size_mb * 1024 * 1024:
                raise InvalidModelParametersError(
                    f"{field_name} reference exceeds {max_size_mb} MB for {spec.title}"
                )


async def validate_owned_reference_sizes(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    spec: ModelSpec,
    parameters: dict[str, Any],
) -> None:
    await validate_reference_sizes(
        session,
        user_id=user_id,
        spec=spec,
        parameters=parameters,
    )
