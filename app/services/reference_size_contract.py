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


async def validate_reference_sizes(
    session: AsyncSession,
    *,
    spec: ModelSpec,
    parameters: dict[str, Any],
    user_id: uuid.UUID | None = None,
) -> None:
    """Enforce known model upload limits before quote/debit.

    Product-owned uploads have measured sizes. Quote can validate by the opaque
    provider URL without a user context; create additionally scopes the same check
    to the current owner. Manual URLs have no trusted byte metadata and are left to
    provider validation unless a model-specific trusted-media rule fails closed.
    """

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

    statement = select(UserReference).where(
        UserReference.status == "ready",
        UserReference.source_url.in_(list(limits_by_url)),
    )
    if user_id is not None:
        statement = statement.where(UserReference.user_id == user_id)
    rows = list((await session.scalars(statement)).all())
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
