import uuid

import pytest

from app.core.config import settings
from app.services import payment_reconciliation
from app.services.payment_reconciliation import PaymentReconciliationService
from app.services.payments import PaymentService


class _Rows:
    def __init__(self, rows: list[tuple[uuid.UUID, str]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[uuid.UUID, str]]:
        return self._rows


class _Session:
    def __init__(self, rows: list[tuple[uuid.UUID, str]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: object) -> _Rows:
        return _Rows(self._rows)


def test_provider_configured_reflects_tbank_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tbank_terminal_key", "")
    monkeypatch.setattr(settings, "tbank_password", "")
    assert PaymentService.provider_configured("tbank") is False

    monkeypatch.setattr(settings, "tbank_terminal_key", "terminal")
    monkeypatch.setattr(settings, "tbank_password", "password")
    assert PaymentService.provider_configured("tbank") is True


@pytest.mark.asyncio
async def test_reconciliation_skips_unconfigured_legacy_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid.uuid4()
    calls: list[uuid.UUID] = []

    monkeypatch.setattr(settings, "tbank_terminal_key", "")
    monkeypatch.setattr(settings, "tbank_password", "")
    monkeypatch.setattr(
        payment_reconciliation,
        "SessionFactory",
        lambda: _Session([(payment_id, "tbank")]),
    )

    async def fake_reconcile(*args: object, **kwargs: object) -> None:
        calls.append(payment_id)

    monkeypatch.setattr(PaymentService, "reconcile", fake_reconcile)

    assert await PaymentReconciliationService.run_once() == 0
    assert calls == []
