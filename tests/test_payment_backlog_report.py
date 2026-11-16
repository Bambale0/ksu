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

class _RequestRows:
    def all(self):
        return [
            ("card", "creation_unknown", "unknown", 54),
            ("card", "creation_unknown", "missing", 10),
            ("cryptobot", "pending", "missing", 2),
        ]


@pytest.mark.asyncio
async def test_request_snapshot_classifies_unknown_and_absent_local_intents():
    session = SimpleNamespace(execute=AsyncMock(return_value=_RequestRows()))
    rows = await PaymentBacklogReport.request_snapshot(session)
    assert rows == [
        {
            "provider": "card", "status": "creation_unknown",
            "request_state": "unknown", "count": 54,
        },
        {
            "provider": "card", "status": "creation_unknown",
            "request_state": "missing", "count": 10,
        },
        {
            "provider": "cryptobot", "status": "pending",
            "request_state": "missing", "count": 2,
        },
    ]
    # Audit is aggregate-only and does not touch the payment ledger.
    for row in rows:
        assert set(row) == {"provider", "status", "request_state", "count"}
    session.execute.assert_awaited_once()
    statement = str(session.execute.await_args.args[0])
    assert "LEFT OUTER JOIN" in statement
    assert "payment_requests" in statement
    assert "UPDATE " not in statement and "INSERT " not in statement


@pytest.mark.asyncio
async def test_request_snapshot_noop_protects_invalid_age():
    with pytest.raises(ValueError, match="older_than_days"):
        await PaymentBacklogReport.request_snapshot(None, older_than_days=0)
    with pytest.raises(ValueError, match="older_than_days"):
        await PaymentBacklogReport.request_snapshot(None, older_than_days=3651)


class _IdentityRows:
    def all(self):
        # Same amount/currency/buyer email remains ambiguous even when
        # different local creation requests exist.
        return [(45, 0), (10, 0), (3, 0), (2, 0), (2, 0), (1, 0), (1, 0)]


@pytest.mark.asyncio
async def test_card_identity_snapshot_only_returns_counts():
    session = SimpleNamespace(execute=AsyncMock(return_value=_IdentityRows()))
    result = await PaymentBacklogReport.card_identity_snapshot(session)
    assert result == {
        "payment_count": 64,
        "signature_groups": 7,
        "repeated_signature_groups": 5,
        "repeated_signature_payments": 62,
        "missing_email_payments": 0,
        "single_signature_payments": 2,
    }
    assert all(isinstance(value, int) for value in result.values())
    assert "email" not in result and "amount" not in result
    session.execute.assert_awaited_once()
    stmt = str(session.execute.await_args.args[0])
    assert "GROUP BY" in stmt
    assert "SELECT" in stmt and "UPDATE " not in stmt


@pytest.mark.asyncio
async def test_card_identity_snapshot_no_email_is_not_unique_identity():
    class Rows:
        def all(self):
            return [(1, 1), (3, 1), (1, 0)]
    session = SimpleNamespace(execute=AsyncMock(return_value=Rows()))
    result = await PaymentBacklogReport.card_identity_snapshot(session)
    assert result["payment_count"] == 5
    assert result["missing_email_payments"] == 4
    assert result["single_signature_payments"] == 1
    assert result["repeated_signature_payments"] == 3


@pytest.mark.asyncio
async def test_card_identity_snapshot_validates_age_without_db_access():
    for age in (0, -1, 3651):
        with pytest.raises(ValueError, match="older_than_days"):
            await PaymentBacklogReport.card_identity_snapshot(None, older_than_days=age)
