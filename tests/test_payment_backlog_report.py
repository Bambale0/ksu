from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.payment_backlog import PaymentBacklogReport


class _Rows:
    def all(self):
        return [
            ("card", "creation_unknown", "missing", "30d_plus", 62),
            ("card", "creation_unknown", "missing", "7_to_30d", 2),
            ("cryptobot", "pending", "present", "30d_plus", 2),
        ]


@pytest.mark.asyncio
async def test_historical_backlog_exposes_aggregate_classification_only():
    session = SimpleNamespace(execute=AsyncMock(return_value=_Rows()))
    result = await PaymentBacklogReport.snapshot(session)
    assert sum(group["count"] for group in result) == 66
    assert result[0] == {
        "provider": "card", "status": "creation_unknown",
        "provider_id": "missing", "age_band": "30d_plus",
        "review_route": "manual_webhook_evidence_review", "count": 62,
    }
    assert result[2]["review_route"] == "authoritative_provider_status_check"
    assert "user_id" not in repr(result)
    assert "external_id" not in repr(result)
    session.execute.assert_awaited_once()


@pytest.mark.parametrize(
    "provider,status,provider_id,route",
    [
        ("card", "creation_unknown", "missing", "manual_webhook_evidence_review"),
        ("cryptobot", "creation_unknown", "missing", "provider_payload_recovery_review"),
        ("tbank", "creating", "missing", "manual_provider_evidence_review"),
        ("tbank", "refund_review", "present", "refund_evidence_review"),
        ("2328", "pending", "present", "authoritative_provider_status_check"),
    ],
)
def test_triage_never_calls_payment_settlement(
    provider: str, status: str, provider_id: str, route: str
) -> None:
    assert PaymentBacklogReport._review_route(provider, status, provider_id) == route


@pytest.mark.asyncio
async def test_backlog_rejects_invalid_age():
    with pytest.raises(ValueError):
        await PaymentBacklogReport.snapshot(None, older_than_days=0)
    with pytest.raises(ValueError):
        await PaymentBacklogReport.snapshot(None, older_than_days=3651)


class _RetryRows:
    def all(self):
        return [
            ("card", "creation_unknown", "manual_card_without_provider_id", 64),
            ("card", "pending", "waiting", 3),
            ("cryptobot", "pending", "due", 2),
            ("tbank", "refund_review", "not_scheduled", 3),
        ]


@pytest.mark.asyncio
async def test_retry_snapshot_has_only_grouped_non_sensitive_fields():
    session = SimpleNamespace(execute=AsyncMock(return_value=_RetryRows()))
    result = await PaymentBacklogReport.retry_snapshot(session)
    assert sum(item["count"] for item in result) == 72
    assert result[0] == {
        "provider": "card",
        "status": "creation_unknown",
        "poll_state": "manual_card_without_provider_id",
        "count": 64,
    }
    assert set(result[-1]) == {"provider", "status", "poll_state", "count"}
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_snapshot_rejects_invalid_age():
    with pytest.raises(ValueError, match="older_than_days"):
        await PaymentBacklogReport.retry_snapshot(None, older_than_days=0)
    with pytest.raises(ValueError, match="older_than_days"):
        await PaymentBacklogReport.retry_snapshot(None, older_than_days=3651)