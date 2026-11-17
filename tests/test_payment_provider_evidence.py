from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.payment_provider_evidence import ProviderEvidenceProbe


def candidate(provider: str = "cryptobot"):
    return SimpleNamespace(
        id=uuid4(), provider=provider, external_id="invoice-42",
        amount=Decimal("120.50"), currency="RUB",
        status="pending", payload={"billing_email": "buyer@example.test"},
    )


def matched_state(payment):
    if payment.provider == "cryptobot":
        return {
            "invoice_id": "invoice-42", "payload": str(payment.id),
            "amount": "120.50", "fiat": "RUB", "status": "paid",
        }
    if payment.provider == "tbank":
        return {
            "PaymentId": "invoice-42", "OrderId": str(payment.id),
            "Amount": 12050, "Status": "CONFIRMED",
        }
    if payment.provider == "2328":
        return {
            "uuid": "invoice-42", "order_id": str(payment.id),
            "amount": "120.50", "currency": "RUB",
            "payment_status": "paid",
        }
    if payment.provider == "card":
        return {
            "id": "invoice-42", "buyerEmail": "buyer@example.test",
            "amount": "120.50", "currency": "RUB",
            "status": "paid",
        }
    raise AssertionError(payment.provider)


@pytest.mark.parametrize("provider", ["cryptobot", "tbank", "2328", "card"])
def test_strict_provider_evidence_require_all_identity_and_money(provider):
    row = candidate(provider)
    state = matched_state(row)
    assert (
        ProviderEvidenceProbe.classify_verified_response(row, state)
        == "verified_provider_paid"
    )
    # A provider's paid flag is never enough without matching invoice identity.
    wrong = dict(state)
    key = {
        "cryptobot": "invoice_id", "tbank": "PaymentId",
        "2328": "uuid", "card": "id",
    }[provider]
    wrong[key] = "another-contract"
    assert (
        ProviderEvidenceProbe.classify_verified_response(row, wrong)
        == "identity_unverified"
    )
    wrong_amount = dict(state)
    wrong_amount["Amount" if provider == "tbank" else "amount"] = (
        12051 if provider == "tbank" else "120.51"
    )
    assert (
        ProviderEvidenceProbe.classify_verified_response(row, wrong_amount)
        == "identity_unverified"
    )
    assert (
        ProviderEvidenceProbe.classify_verified_response(row, None)
        == "provider_not_found_unproven"
    )


@pytest.mark.parametrize("provider", ["cryptobot", "tbank", "2328", "card"])
def test_local_owner_binding_required_for_paid_status(provider):
    row = candidate(provider)
    state = matched_state(row)
    identity_key = {
        "cryptobot": "payload", "tbank": "OrderId",
        "2328": "order_id", "card": "buyerEmail",
    }[provider]
    state[identity_key] = (
        "other@example.test" if provider == "card" else str(uuid4())
    )
    assert ProviderEvidenceProbe.classify_verified_response(
        row, state
    ) == "identity_unverified"


@pytest.mark.parametrize(
    ("provider", "status_key", "status", "outcome"),
    [
        ("cryptobot", "status", "active", "verified_provider_pending"),
        ("cryptobot", "status", "expired", "verified_provider_terminal"),
        ("tbank", "Status", "AUTHORIZED", "verified_provider_pending"),
        ("tbank", "Status", "REFUNDED", "provider_refund_evidence"),
        ("2328", "payment_status", "pending", "verified_provider_pending"),
        ("2328", "payment_status", "cancel", "verified_provider_terminal"),
        ("card", "status", "pending", "verified_provider_pending"),
        ("card", "status", "refunded", "provider_refund_evidence"),
    ],
)
def test_provider_status_categories_are_observations_not_settlements(
    provider, status_key, status, outcome
):
    row = candidate(provider)
    state = matched_state(row)
    state[status_key] = status
    assert ProviderEvidenceProbe.classify_verified_response(row, state) == outcome


@pytest.mark.parametrize("provider", ["cryptobot", "2328"])
def test_provider_evidence_requires_explicit_currency(provider):
    row = candidate(provider)
    state = matched_state(row)
    state.pop("fiat" if provider == "cryptobot" else "currency")
    assert ProviderEvidenceProbe.classify_verified_response(
        row, state
    ) == "identity_unverified"


@pytest.mark.parametrize("age,limit", [(0, 2), (3651, 2), (7, 0), (7, 6)])
@pytest.mark.asyncio
async def test_probe_rejects_unbounded_queries_without_database(age, limit):
    with pytest.raises(ValueError):
        await ProviderEvidenceProbe.candidates(
            None, provider="tbank", limit=limit, older_than_days=age
        )


@pytest.mark.asyncio
async def test_candidates_are_detached_snapshots_from_select_only():
    row = candidate("tbank")

    class _Rows:
        def all(self):
            return [row]

    session = SimpleNamespace(scalars=AsyncMock(return_value=_Rows()))
    result = await ProviderEvidenceProbe.candidates(
        session, provider="tbank", limit=2, older_than_days=7
    )
    assert len(result) == 1
    assert result[0].id == row.id
    assert result[0].external_id == "invoice-42"
    assert result[0].payload is not row.payload
    statement = str(session.scalars.await_args.args[0])
    assert "SELECT" in statement
    assert "payments.external_id IS NOT NULL" in statement
    assert "UPDATE " not in statement and "DELETE " not in statement
    session.scalars.assert_awaited_once()


@pytest.mark.asyncio
async def test_provider_lookup_failure_does_not_expose_invoice_or_credentials(
    monkeypatch
):
    row = candidate("card")
    async def fail(_row):
        raise RuntimeError("https://secret.example/invoice-42?token=confidential")
    monkeypatch.setattr(ProviderEvidenceProbe, "lookup_status", fail)
    assert await ProviderEvidenceProbe.probe(row) == "provider_lookup_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("probe_enabled", [False, True])
async def test_audit_cli_uses_readonly_transaction_and_aggregate_only(
    monkeypatch, capsys, probe_enabled
):
    script = Path(__file__).resolve().parents[1] / "scripts/audit_provider_payment_evidence.py"
    spec = importlib.util.spec_from_file_location("audit_provider_payment_evidence", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    class _Session:
        def __init__(self):
            self.execute = AsyncMock()
            self.rollback = AsyncMock()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    session = _Session()
    monkeypatch.setattr(cli, "SessionFactory", lambda: session)
    dispose = AsyncMock()
    monkeypatch.setattr(cli, "engine", SimpleNamespace(dispose=dispose))
    row = candidate("card")
    selected = AsyncMock(return_value=[row])
    probe = AsyncMock(return_value="verified_provider_pending")
    monkeypatch.setattr(cli.ProviderEvidenceProbe, "candidates", selected)
    monkeypatch.setattr(cli.ProviderEvidenceProbe, "probe", probe)
    argv = ["audit_provider_payment_evidence", "--provider", "card", "--limit", "1"]
    if probe_enabled:
        argv += ["--probe"]
    monkeypatch.setattr(sys, "argv", argv)
    await cli.main()
    data = json.loads(capsys.readouterr().out)
    assert data["provider"] == "card"
    assert data["selected"] == 1
    assert data["evidence_required"] is True
    assert data["automatic_settlement_allowed"] is False
    assert data["changes_to_payments_or_wallets"] is False
    assert data["outcome_counts"] == (
        {"verified_provider_pending": 1} if probe_enabled else {}
    )
    assert "buyer@" not in json.dumps(data)
    assert "invoice-42" not in json.dumps(data)
    assert "120.50" not in json.dumps(data)
    if probe_enabled:
        probe.assert_awaited_once()
    else:
        probe.assert_not_awaited()
    assert str(session.execute.await_args.args[0]) == "SET TRANSACTION READ ONLY"
    session.rollback.assert_awaited_once()
    dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-1, 501])
async def test_evidence_offset_rejects_unbounded_windows_before_db(offset):
    with pytest.raises(ValueError, match="offset"):
        await ProviderEvidenceProbe.candidates(
            None, provider="card", limit=5, offset=offset,
        )


@pytest.mark.asyncio
async def test_evidence_candidates_use_stable_bounded_page_offset():
    row = candidate("card")

    class _Rows:
        def all(self):
            return [row]

    session = SimpleNamespace(scalars=AsyncMock(return_value=_Rows()))
    selected = await ProviderEvidenceProbe.candidates(
        session, provider="card", limit=2, offset=5,
    )
    assert len(selected) == 1
    stmt = str(session.scalars.await_args.args[0])
    assert "ORDER BY" in stmt and "LIMIT" in stmt and "OFFSET" in stmt
    compiled = session.scalars.await_args.args[0].compile()
    assert 5 in compiled.params.values()
    assert 2 in compiled.params.values()
    assert "UPDATE " not in stmt and "DELETE " not in stmt


@pytest.mark.asyncio
async def test_evidence_cli_offset_survives_readonly_and_output(monkeypatch, capsys):
    script = Path(__file__).resolve().parents[1] / "scripts/audit_provider_payment_evidence.py"
    spec = importlib.util.spec_from_file_location("audit_evidence_offset", script)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    class Session:
        execute = AsyncMock()
        rollback = AsyncMock()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None

    session = Session()
    monkeypatch.setattr(cli, "SessionFactory", lambda: session)
    monkeypatch.setattr(cli, "engine", SimpleNamespace(dispose=AsyncMock()))
    selected = AsyncMock(return_value=[candidate("card")])
    query_provider = AsyncMock()
    monkeypatch.setattr(cli.ProviderEvidenceProbe, "candidates", selected)
    monkeypatch.setattr(cli.ProviderEvidenceProbe, "probe", query_provider)
    monkeypatch.setattr(sys, "argv", [
        "audit_provider_payment_evidence", "--provider", "card",
        "--limit", "1", "--offset", "5",
    ])
    await cli.main()
    data = json.loads(capsys.readouterr().out)
    assert data["offset"] == 5
    assert data["selected"] == 1
    assert data["mode"] == "local_read_only"
    assert data["automatic_settlement_allowed"] is False
    assert data["changes_to_payments_or_wallets"] is False
    assert selected.await_args.kwargs["offset"] == 5
    query_provider.assert_not_awaited()
    assert str(session.execute.await_args.args[0]) == "SET TRANSACTION READ ONLY"
