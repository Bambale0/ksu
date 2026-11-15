from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.payment_backlog import PaymentBacklogReport


class _Rows:
    def all(self):
        return [("card", "creation_unknown", "missing", 64),
                ("cryptobot", "pending", "present", 2)]


@pytest.mark.asyncio
async def test_historical_backlog_exposes_aggregate_counts_only():
    session = SimpleNamespace(execute=AsyncMock(return_value=_Rows()))
    result = await PaymentBacklogReport.snapshot(session)
    assert result == [
        {"provider": "card", "status": "creation_unknown", "provider_id": "missing", "count": 64},
        {"provider": "cryptobot", "status": "pending", "provider_id": "present", "count": 2},
    ]
    assert "user_id" not in repr(result)
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_backlog_rejects_invalid_age():
    with pytest.raises(ValueError):
        await PaymentBacklogReport.snapshot(None, older_than_days=0)