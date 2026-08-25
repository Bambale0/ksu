from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.pinterest_flow import PinterestFlowService
from app.services.trends import TrendService


@pytest.mark.asyncio
async def test_pinterest_catalog_filters_generic_trends(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    pinterest = SimpleNamespace(
        id="pinterest",
        title="Pinterest Editorial",
        payload={"tags": ["pinterest"]},
        is_active=True,
        created_at=now,
    )
    generic = SimpleNamespace(
        id="generic",
        title="Editorial",
        payload={"tags": ["portrait"]},
        is_active=True,
        created_at=now,
    )
    scalars = AsyncMock()
    scalars.return_value.all.return_value = [generic, pinterest]
    session = AsyncMock()
    session.scalars = scalars

    public_view = AsyncMock(return_value={"id": "pinterest", "sort_order": 1, "created_at": now.isoformat()})
    monkeypatch.setattr(TrendService, "public_view", public_view)

    payload = await PinterestFlowService.list_public(session, limit=20)

    assert payload["items"] == [{"id": "pinterest", "sort_order": 1, "created_at": now.isoformat()}]
    public_view.assert_awaited_once_with(session, pinterest)
