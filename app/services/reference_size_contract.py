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
        return [str(item) for item in value if isinstance(item, str) and item]
    return []


async def validate_owned_reference_sizes(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    spec: ModelSpec,
    parameters: dict[str, Any],
) -> None:
    """Enforce model upload limits for product-owned references before debit.

    External/manual URLs have no trusted byte metadata and continue to provider
    validation. Files uploaded through ROXY have a measured size and must obey the
    exact max_size_mb exposed by the resolved model's public ui_schema.
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

    rows = list(
        (
            await session.scalars(
                select(UserReference).where(
                    UserReference.user_id == user_id,
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
