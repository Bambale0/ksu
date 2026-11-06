from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import (
    Payment,
    PromoCode,
    PromoRedemption,
    ReferralRelation,
    User,
    WalletTransaction,
)
from app.db.payment_models import PaymentRequest
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import CreatedPayment, PaymentProviderValidationError
from app.services.card_payments import CardPaymentService


@pytest.fixture(autouse=True)
def configured_package(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "rox_packages_json", "{}")
    monkeypatch.setattr(settings, "card_offer_id", "catalog-price-offer")
    monkeypatch.setattr(settings, "card_packages_json", """{
        "catalog-price": {"credits": "1000", "prices": {"RUB": "1087.00"},
                          "offer_id": "catalog-price-offer"}
    }""")


def catalog(prices: list[dict[str, Any]]) -> dict[str, Any]:
    return {"items": [{"offers": [{"id": "catalog-price-offer", "prices": prices}]}]}


def user(name: str) -> User:
    return User(
        telegram_id=9_700_000_000_000 + uuid.uuid4().int % 100_000_000_000,
        first_name=name, is_active=True,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "catalog_amount",
    ["invalid", "NaN", "sNaN", "Infinity", "-Infinity", {"unexpected": "value"}],
    ids=["nonnumeric", "nan", "signaling-nan", "positive-infinity", "negative-infinity", "object"],
)
async def test_malformed_catalog_price_terminalizes_real_promo_checkout(
    monkeypatch: pytest.MonkeyPatch,
    catalog_amount: Any,
) -> None:
    remote_calls = 0
    catalog_calls = 0

    async def get_products(self: CardCheckoutClient) -> dict[str, Any]:
        nonlocal catalog_calls
        catalog_calls += 1
        return catalog([{"currency": "RUB", "amount": catalog_amount}])

    async def create_invoice(self: CardCheckoutClient, **kwargs: object) -> CreatedPayment:
        nonlocal remote_calls
        remote_calls += 1
        raise AssertionError("Malformed catalog must never reach remote invoice creation")

    monkeypatch.setattr(CardCheckoutClient, "get_products", get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", create_invoice)
    async with SessionFactory() as session:
        partner, buyer = user("Catalog partner"), user("Catalog buyer")
        session.add_all([partner, buyer])
        await session.flush()
        promo = PromoCode(
            code=f"CATALOG{uuid.uuid4().hex[:12].upper()}",
            reward_amount=Decimal("7"), partner_user_id=partner.id,
            max_uses=10, uses_count=0, is_active=True,
        )
        session.add(promo)
        await session.commit()
        request = dict(
            user_id=buyer.id, package_id="catalog-price", currency="RUB",
            billing_email="catalog-buyer@example.invalid",
            request_key=str(uuid.uuid4()), promo_code=promo.code,
        )
        error: Exception | None = None
        try:
            await CardPaymentService.create(session, **request)
        except Exception as exc:
            error = exc

        payment = await session.scalar(select(Payment).where(Payment.user_id == buyer.id))
        assert payment is not None
        assert remote_calls == 0
        assert payment.status == "failed"
        assert payment.external_id is None
        assert payment.payload.get("provider_error_type") == "validation"
        creation = await session.scalar(
            select(PaymentRequest).where(PaymentRequest.payment_id == payment.id)
        )
        assert creation is not None and creation.status == "failed"
        assert isinstance(error, PaymentProviderValidationError)

        # Current promo activation is independent from payment success.
        relation = await session.get(ReferralRelation, buyer.id)
        assert relation is not None and relation.promo_id == promo.id
        assert relation.inviter_user_id == partner.id
        await session.refresh(promo)
        assert promo.uses_count == 1
        assert not list((await session.scalars(
            select(PromoRedemption).where(
                PromoRedemption.payment_id == payment.id,
                PromoRedemption.status == "pending",
            )
        )).all())
        assert not list((await session.scalars(
            select(WalletTransaction).where(WalletTransaction.user_id == buyer.id)
        )).all())

        replay = await CardPaymentService.create(session, **request)
        assert replay.id == payment.id and replay.status == "failed"
        assert catalog_calls == 1 and remote_calls == 0
        await session.refresh(promo)
        assert promo.uses_count == 1


@pytest.mark.asyncio
async def test_malformed_catalog_price_releases_pending_legacy_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote_calls = 0
    async with SessionFactory() as session:
        buyer = user("Legacy catalog reservation")
        session.add(buyer)
        await session.flush()
        promo = PromoCode(
            code=f"CATLEGACY{uuid.uuid4().hex[:12].upper()}",
            reward_amount=Decimal("7"), partner_user_id=None,
            max_uses=1, uses_count=0, is_active=True,
        )
        session.add(promo)
        await session.commit()

        async def get_products(self: CardCheckoutClient) -> dict[str, Any]:
            # A synthetic historical reservation is installed at the committed
            # pre-provider boundary; payment creation and cleanup remain real.
            async with SessionFactory() as legacy_session:
                payment = await legacy_session.scalar(
                    select(Payment).where(Payment.user_id == buyer.id)
                )
                assert payment is not None and payment.status == "creating"
                legacy_session.add(PromoRedemption(
                    promo_id=promo.id, user_id=buyer.id, payment_id=payment.id,
                    status="pending", reserved_until=datetime.now(UTC) + timedelta(hours=1),
                ))
                await legacy_session.commit()
            return catalog([{"currency": "RUB", "amount": "not-a-price"}])

        async def create_invoice(self: CardCheckoutClient, **kwargs: object) -> CreatedPayment:
            nonlocal remote_calls
            remote_calls += 1
            raise AssertionError("Malformed catalog must never create an invoice")

        monkeypatch.setattr(CardCheckoutClient, "get_products", get_products)
        monkeypatch.setattr(CardCheckoutClient, "create_invoice", create_invoice)
        error: Exception | None = None
        try:
            await CardPaymentService.create(
                session, user_id=buyer.id, package_id="catalog-price", currency="RUB",
                billing_email="legacy-catalog@example.invalid", request_key=str(uuid.uuid4()),
            )
        except Exception as exc:
            error = exc
        reservation = await session.scalar(
            select(PromoRedemption).where(PromoRedemption.user_id == buyer.id)
        )
        assert reservation is not None
        assert reservation.status == "released"
        assert reservation.reserved_until is None and reservation.redeemed_at is None
        await session.refresh(promo)
        assert promo.uses_count == 0
        assert isinstance(error, PaymentProviderValidationError)
        assert remote_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", ["1087.000", "1.087E+3"])
async def test_finite_catalog_price_ignores_unsupported_currency_noise(
    monkeypatch: pytest.MonkeyPatch,
    amount: str,
) -> None:
    remote_calls = 0
    external_id = str(uuid.uuid4())

    async def get_products(self: CardCheckoutClient) -> dict[str, Any]:
        return catalog([
            {"currency": "BTC", "amount": "not-a-number"},
            {"currency": "XYZ", "amount": "sNaN"},
            {"currency": "RUB", "amount": amount},
        ])

    async def create_invoice(self: CardCheckoutClient, **kwargs: object) -> CreatedPayment:
        nonlocal remote_calls
        remote_calls += 1
        assert kwargs["amount"] is None
        return CreatedPayment(
            external_id=external_id, payment_url="https://pay.example.invalid/catalog",
            raw={"id": external_id, "amount": "1087.00", "currency": "RUB"},
        )

    monkeypatch.setattr(CardCheckoutClient, "get_products", get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", create_invoice)
    async with SessionFactory() as session:
        buyer = user("Finite catalog")
        session.add(buyer)
        await session.commit()
        request = dict(
            user_id=buyer.id, package_id="catalog-price", currency="RUB",
            billing_email="finite-catalog@example.invalid", request_key=str(uuid.uuid4()),
        )
        payment = await CardPaymentService.create(session, **request)
        assert payment.status == "pending"
        assert payment.external_id == external_id
        assert payment.amount == Decimal("1087.00")
        replay = await CardPaymentService.create(session, **request)
        assert replay.id == payment.id and remote_calls == 1
