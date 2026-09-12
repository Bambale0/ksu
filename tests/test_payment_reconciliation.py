import uuid
from decimal import Decimal

import httpx
import pytest

from app.core.config import settings
from app.db.models import Payment
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import PaymentProviderValidationError
from app.services import payment_reconciliation
from app.services.card_payments import CardPaymentService
from app.services.payment_reconciliation import PaymentReconciliationService
from app.services.payments import PaymentService


class _Rows:
    def __init__(self, rows: list[tuple[uuid.UUID, str, str | None]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[uuid.UUID, str, str | None]]:
        return self._rows


class _Session:
    def __init__(self, rows: list[tuple[uuid.UUID, str, str | None]]) -> None:
        self._rows = rows

    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: object) -> _Rows:
        return _Rows(self._rows)


class _PaymentSession:
    def __init__(self, payment: Payment) -> None:
        self.payment = payment
        self.commits = 0

    async def get(self, model: object, payment_id: uuid.UUID) -> Payment | None:
        if model is Payment and payment_id == self.payment.id:
            return self.payment
        return None

    async def commit(self) -> None:
        self.commits += 1


def _payment(*, external_id: str | None, package_id: str = "starter") -> Payment:
    return Payment(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider="yookassa",
        external_id=external_id,
        amount=Decimal("300.00"),
        currency="RUB",
        rox_amount=Decimal("300.00"),
        status="pending",
        payload={"package_id": package_id},
    )


def _card_payment(*, external_id: str) -> Payment:
    return Payment(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        provider="card",
        external_id=external_id,
        amount=Decimal("300.00"),
        currency="RUB",
        rox_amount=Decimal("300.00"),
        status="pending",
        payload={"package_id": "starter"},
    )


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
        lambda: _Session([(payment_id, "tbank", "provider-id")]),
    )

    async def fake_reconcile(*args: object, **kwargs: object) -> None:
        calls.append(payment_id)

    monkeypatch.setattr(PaymentService, "reconcile", fake_reconcile)

    assert await PaymentReconciliationService.run_once() == 0
    assert calls == []


@pytest.mark.asyncio
async def test_reconciliation_skips_card_intent_without_external_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid.uuid4()
    calls: list[uuid.UUID] = []

    monkeypatch.setattr(settings, "card_api_key", "key")
    monkeypatch.setattr(
        payment_reconciliation,
        "SessionFactory",
        lambda: _Session([(payment_id, "card", None)]),
    )

    async def fake_reconcile(*args: object, **kwargs: object) -> None:
        calls.append(payment_id)

    monkeypatch.setattr(CardPaymentService, "reconcile", fake_reconcile)

    assert await PaymentReconciliationService.run_once() == 0
    assert calls == []


@pytest.mark.asyncio
async def test_card_lookup_rejection_becomes_terminal_reconciliation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _card_payment(external_id="invalid-provider-id")
    session = _PaymentSession(payment)

    class _RejectedCardClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def get_invoice(self, external_id: str) -> dict[str, object]:
            raise PaymentProviderValidationError(
                "Card checkout invoice lookup rejected: HTTP 400"
            )

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("app.services.card_payments.CardCheckoutClient", _RejectedCardClient)

    result = await CardPaymentService.reconcile(session, payment_id=payment.id)

    assert result.status == "failed"
    assert session.commits == 1
    assert result.payload["reconciliation_terminal_error"]["reason"] == "provider_lookup_rejected"


@pytest.mark.asyncio
async def test_card_client_classifies_deterministic_lookup_4xx_as_validation_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "Invalid request"}, request=request)

    client = CardCheckoutClient("key", "https://gate.lava.test")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://gate.lava.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(PaymentProviderValidationError, match="lookup rejected: HTTP 400"):
            await client.get_invoice("bad-id")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_yookassa_reconciliation_marks_missing_provider_payment_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment(external_id="provider-1")
    session = _PaymentSession(payment)

    class _MissingYooKassaClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def get_payment(self, external_id: str) -> dict[str, object]:
            request = httpx.Request("GET", f"https://api.yookassa.ru/v3/payments/{external_id}")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("app.services.payments.YooKassaClient", _MissingYooKassaClient)

    result = await PaymentService.reconcile(session, payment_id=payment.id)

    assert result.status == "failed"
    assert session.commits == 1
    assert result.payload["reconciliation_terminal_error"]["reason"] == "provider_not_found"
    assert result.payload["reconciliation_terminal_error"]["external_id"] == "provider-1"


@pytest.mark.asyncio
async def test_yookassa_reconciliation_marks_unknown_package_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment = _payment(external_id=None, package_id="starter")
    session = _PaymentSession(payment)
    create_calls: list[str] = []

    class _YooKassaClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            return None

        async def create_payment(self, **kwargs: object) -> object:
            create_calls.append(str(kwargs))
            raise AssertionError("unknown package must fail before creating a provider payment")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(settings, "rox_packages_json", "{}")
    monkeypatch.setattr("app.services.payments.YooKassaClient", _YooKassaClient)

    result = await PaymentService.reconcile(session, payment_id=payment.id)

    assert result.status == "failed"
    assert session.commits == 1
    assert create_calls == []
    assert result.payload["reconciliation_terminal_error"]["reason"] == "unknown_package"
