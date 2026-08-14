from __future__ import annotations

import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import Payment, ReferralReward, ReferralRelation, User, Wallet
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import PaymentProviderError
from app.services.card_payments import CardPackageCatalog, CardPaymentService

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_LABEL = "Оплата картой · USD / EUR / RUB / СБП"


def _telegram_id() -> int:
    return 98_000_000_000_000 + random.randint(1, 999_999_999)


def test_official_card_routes_are_currency_scoped() -> None:
    assert CardCheckoutClient.SUPPORTED_PAYMENT_PROVIDERS == {
        "RUB": frozenset({"BANK131"}),
        "USD": frozenset({"UNLIMINT", "PAYPAL", "STRIPE"}),
        "EUR": frozenset({"UNLIMINT", "PAYPAL", "STRIPE"}),
    }
    CardCheckoutClient.validate_route("RUB", "BANK131")
    CardCheckoutClient.validate_route("USD", "UNLIMINT")
    CardCheckoutClient.validate_route("USD", "PAYPAL")
    CardCheckoutClient.validate_route("EUR", "STRIPE")
    with pytest.raises(PaymentProviderError):
        CardCheckoutClient.validate_route("RUB", "PAYPAL")
    with pytest.raises(PaymentProviderError):
        CardCheckoutClient.validate_route("USD", "BANK131")


def test_official_custom_price_limits_are_enforced() -> None:
    for currency, minimum, maximum in (
        ("RUB", Decimal("50"), Decimal("1000000")),
        ("USD", Decimal("5"), Decimal("10000")),
        ("EUR", Decimal("5"), Decimal("10000")),
    ):
        CardCheckoutClient.validate_amount(currency, minimum)
        CardCheckoutClient.validate_amount(currency, maximum)
        with pytest.raises(PaymentProviderError):
            CardCheckoutClient.validate_amount(currency, minimum - Decimal("0.01"))
        with pytest.raises(PaymentProviderError):
            CardCheckoutClient.validate_amount(currency, maximum + Decimal("0.01"))


def test_card_package_prices_are_explicit_and_never_fx_derived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"starter":{"credits":"300","prices":{"RUB":"300","USD":"6.00","EUR":"5.70"}}}',
    )
    package = CardPackageCatalog.package("starter")
    assert package.credits == Decimal("300")
    assert package.prices == {
        "RUB": Decimal("300"),
        "USD": Decimal("6.00"),
        "EUR": Decimal("5.70"),
    }


def test_empty_card_catalog_only_inherits_legacy_rub_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "card_packages_json", "{}")
    monkeypatch.setattr(settings, "internal_credit_rub", Decimal("1"))
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"starter":{"credits":"300","currency":"RUB"}}',
    )
    package = CardPackageCatalog.package("starter")
    assert package.prices == {"RUB": Decimal("300.00")}
    assert "USD" not in package.prices
    assert "EUR" not in package.prices


def test_card_webhook_key_is_required_and_constant_compared() -> None:
    client = CardCheckoutClient("", "https://example.invalid", "webhook-secret")
    assert client.verify_webhook_key("webhook-secret")
    assert not client.verify_webhook_key("wrong")
    assert not client.verify_webhook_key(None)


def test_public_payment_surface_is_vendor_neutral() -> None:
    public_files = [
        ROOT / "app" / "api" / "v1" / "card_payments.py",
        ROOT / "app" / "api" / "v1" / "card_webhooks.py",
        ROOT / "app" / "web" / "mini_app" / "primary-card-checkout.js",
        ROOT / "app" / "web" / "mini_app" / "account-overview.js",
        ROOT / "app" / "bot" / "handlers" / "start.py",
        ROOT / "app" / "bot" / "keyboards.py",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in public_files)
    webhook_source = (ROOT / "app" / "api" / "card_webhooks.py").read_text(encoding="utf-8")
    main_source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert PUBLIC_LABEL in combined
    assert 'APIRouter(prefix="/webhooks"' in webhook_source
    assert '@router.post("/payments/card"' in webhook_source
    assert "app.include_router(card_webhook_router)" in main_source
    assert "lava" not in combined.lower()
    assert "lavatop" not in combined.lower()


def test_provider_adapter_uses_documented_invoice_contract() -> None:
    source = (ROOT / "app" / "providers" / "card_checkout.py").read_text(encoding="utf-8")
    assert '"/api/v3/invoice"' in source
    assert 'f"/api/v2/invoices/{invoice_id}"' in source
    assert '"X-Api-Key"' in source
    for field in ("email", "offerId", "currency", "amount", "paymentProvider"):
        assert field in source


def test_primary_checkout_requires_second_direct_click_to_open_url() -> None:
    source = (
        ROOT / "app" / "web" / "mini_app" / "primary-card-checkout.js"
    ).read_text(encoding="utf-8")
    assert 'pay.textContent = "Создать оплату"' in source
    assert '"Открыть оплату"' in source
    create_call = source.index('api("/api/v1/payments/card/checkout"')
    nearby_after_create = source[create_call : create_call + 1000]
    assert "openUrl(payment.payment_url)" not in nearby_after_create
    assert "if (canOpenCurrent())" in source
    assert "openUrl(state.current.payment_url)" in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source


@pytest.mark.asyncio
async def test_invalid_configured_price_is_rejected_before_payment_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"starter":{"credits":"300","prices":{"USD":"4.00"}}}',
    )
    async with SessionFactory() as session:
        buyer = User(telegram_id=_telegram_id(), first_name="Invalid price")
        session.add(buyer)
        await session.commit()

        with pytest.raises(PaymentProviderError):
            await CardPaymentService.create(
                session,
                user_id=buyer.id,
                package_id="starter",
                currency="USD",
                billing_email="buyer@example.com",
                request_key=str(uuid.uuid4()),
            )

        payment_count = await session.scalar(
            select(func.count()).select_from(Payment).where(Payment.user_id == buyer.id)
        )
        assert int(payment_count or 0) == 0


@pytest.mark.asyncio
async def test_usd_card_payment_credits_once_and_referral_uses_purchased_rox_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "internal_credit_rub", Decimal("1"))
    async with SessionFactory() as session:
        inviter = User(telegram_id=_telegram_id(), first_name="Referrer")
        buyer = User(telegram_id=_telegram_id(), first_name="Buyer")
        session.add_all([inviter, buyer])
        await session.flush()
        session.add(
            ReferralRelation(referred_user_id=buyer.id, inviter_user_id=inviter.id)
        )
        payment = Payment(
            user_id=buyer.id,
            provider="card",
            external_id=f"card-{uuid.uuid4()}",
            amount=Decimal("6.00"),
            currency="USD",
            rox_amount=Decimal("300.00"),
            status="pending",
            payload={},
        )
        session.add(payment)
        await session.commit()

        await CardPaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "success"},
        )
        await CardPaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "success"},
        )

        wallet = await session.get(Wallet, buyer.id)
        reward = await session.scalar(
            select(ReferralReward).where(ReferralReward.partner_user_id == inviter.id)
        )
        reward_count = await session.scalar(
            select(func.count()).select_from(ReferralReward).where(
                ReferralReward.partner_user_id == inviter.id
            )
        )
        assert wallet is not None
        assert wallet.balance == Decimal("300.00")
        assert reward is not None
        assert reward.amount == Decimal("90.00")
        assert int(reward_count or 0) == 1
