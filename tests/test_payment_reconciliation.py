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

    async def scalar(self, statement: object) -> Payment:
        return self.payment

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


@pytest.mark.asyncio
async def test_reconciliation_backs_off_transient_failures_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid.uuid4()
    calls: list[uuid.UUID] = []
    clock = [1000.0]
    monkeypatch.setattr(PaymentReconciliationService, "_retry_after", {})
    monkeypatch.setattr(PaymentReconciliationService, "_failure_counts", {})
    monkeypatch.setattr(payment_reconciliation.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(payment_reconciliation.random, "uniform", lambda a, b: 1.0)
    monkeypatch.setattr(
        payment_reconciliation,
        "SessionFactory",
        lambda: _Session([(payment_id, "cryptopay", "invoice-1")]),
    )
    monkeypatch.setattr(PaymentService, "provider_configured", lambda provider: True)

    async def transient_failure(*args: object, **kwargs: object) -> None:
        calls.append(payment_id)
        if len(calls) == 1:
            raise RuntimeError("temporary provider outage")

    monkeypatch.setattr(PaymentService, "reconcile", transient_failure)
    assert await PaymentReconciliationService.run_once() == 0
    assert len(calls) == 1
    assert await PaymentReconciliationService.run_once() == 0
    assert len(calls) == 1
    clock[0] += 61
    assert await PaymentReconciliationService.run_once() == 1
    assert len(calls) == 2
    assert payment_id not in PaymentReconciliationService._failure_counts


@pytest.mark.asyncio
async def test_reconciliation_cooldown_grows_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid.uuid4()
    clock = [1000.0]
    attempts = [0]
    monkeypatch.setattr(PaymentReconciliationService, "_retry_after", {})
    monkeypatch.setattr(PaymentReconciliationService, "_failure_counts", {})
    monkeypatch.setattr(payment_reconciliation.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(payment_reconciliation.random, "uniform", lambda a, b: 1.0)
    monkeypatch.setattr(
        payment_reconciliation,
        "SessionFactory",
        lambda: _Session([(payment_id, "cryptopay", "invoice-1")]),
    )
    monkeypatch.setattr(PaymentService, "provider_configured", lambda provider: True)

    async def always_fail(*args: object, **kwargs: object) -> None:
        attempts[0] += 1
        raise RuntimeError("temporary outage")

    monkeypatch.setattr(PaymentService, "reconcile", always_fail)
    assert await PaymentReconciliationService.run_once() == 0
    assert PaymentReconciliationService._retry_after[payment_id] == 1060.0
    clock[0] = 1060.0
    assert await PaymentReconciliationService.run_once() == 0
    assert PaymentReconciliationService._retry_after[payment_id] == 1180.0
    assert attempts[0] == 2


@pytest.mark.asyncio
async def test_reconciliation_skips_cooling_payment_without_starving_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cooling_id, ready_id = uuid.uuid4(), uuid.uuid4()
    calls: list[uuid.UUID] = []
    monkeypatch.setattr(settings, "payment_reconcile_batch_size", 1)
    monkeypatch.setattr(PaymentReconciliationService, "_retry_after", {cooling_id: 2000.0})
    monkeypatch.setattr(PaymentReconciliationService, "_failure_counts", {cooling_id: 1})
    monkeypatch.setattr(payment_reconciliation.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(
        payment_reconciliation,
        "SessionFactory",
        lambda: _Session([
            (cooling_id, "cryptopay", "invoice-1"),
            (ready_id, "cryptopay", "invoice-2"),
        ]),
    )
    monkeypatch.setattr(PaymentService, "provider_configured", lambda provider: True)

    async def fake_reconcile(*args: object, **kwargs: object) -> None:
        calls.append(kwargs["payment_id"])

    monkeypatch.setattr(PaymentService, "reconcile", fake_reconcile)
    assert await PaymentReconciliationService.run_once() == 1
    assert calls == [ready_id]


class _SharedCooldownRedis:
    def __init__(self) -> None:
        self.keys: dict[str, int] = {}

    async def exists(self, key: str) -> int:
        return int(key in self.keys)

    async def set(self, key: str, value: str, *, ex: int) -> bool:
        self.keys[key] = ex
        return True


@pytest.mark.asyncio
async def test_reconciliation_cooldown_survives_worker_process_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid.uuid4()
    shared = _SharedCooldownRedis()
    attempts = 0

    monkeypatch.setattr(settings, "cryptopay_api_token", "configured")
    monkeypatch.setattr(
        payment_reconciliation,
        "SessionFactory",
        lambda: _Session([(payment_id, "cryptobot", "invoice-123")]),
    )

    async def fail_provider(*args: object, **kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("temporary provider failure")

    monkeypatch.setattr(PaymentService, "reconcile", fail_provider)
    PaymentReconciliationService._retry_after.clear()
    PaymentReconciliationService._failure_counts.clear()
    try:
        assert await PaymentReconciliationService.run_once(redis=shared) == 0
        assert attempts == 1
        assert shared.keys[f"ksu:payment-reconcile:cooldown:{payment_id}"] >= 1
        # Simulate a worker restart: process-local cooldown is lost.
        PaymentReconciliationService._retry_after.clear()
        PaymentReconciliationService._failure_counts.clear()
        assert await PaymentReconciliationService.run_once(redis=shared) == 0
        assert attempts == 1
    finally:
        PaymentReconciliationService._retry_after.clear()
        PaymentReconciliationService._failure_counts.clear()


def test_trend_409_exposes_stable_business_code() -> None:
    from app.api.v1.trends import _domain_error
    from app.services.trend_workflows import TrendWorkflowConflict
    from app.services.wallet import InsufficientBalanceError

    conflict = _domain_error(TrendWorkflowConflict("request already started"))
    assert conflict.status_code == 409
    assert conflict.headers == {"X-Trend-Failure-Code": "workflow_conflict"}
    # Avoid relying on the wallet exception constructor signature.
    low_balance = _domain_error(InsufficientBalanceError.__new__(InsufficientBalanceError))
    assert low_balance.status_code == 409
    assert low_balance.headers == {"X-Trend-Failure-Code": "insufficient_credits"}