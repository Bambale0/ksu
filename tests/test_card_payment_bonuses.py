from __future__ import annotations

import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.api.v1.card_payments import packages as package_view
from app.core.config import settings
from app.db.models import User, Wallet
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import CreatedPayment
from app.services.card_payments import CardPackage, CardPackageCatalog, CardPaymentService
from app.services.payment_bonuses import TopUpBonusService
from app.services.referrals import ReferralService

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "mini-app"

PACKAGES_JSON = """
{
  "p100": {"credits": "100", "prices": {"RUB": "108.7"}},
  "p300": {"credits": "300", "prices": {"RUB": "326.1"}},
  "p500": {"credits": "500", "prices": {"RUB": "543.5"}},
  "p1000": {"credits": "1000", "prices": {"RUB": "1087"}},
  "p2000": {"credits": "2000", "prices": {"RUB": "2174"}},
  "p5000": {"credits": "5000", "prices": {"RUB": "5435"}}
}
"""


def _telegram_id() -> int:
    return 99_400_000_000_000 + random.randint(1, 999_999_999)


@pytest.mark.asyncio
async def test_card_package_endpoint_exposes_rox_gift_bonuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "card_packages_json", PACKAGES_JSON)

    payload = await package_view()
    packages = payload["packages"]

    assert packages["p100"]["bonus_credits"] == "0"
    assert packages["p100"]["total_credits"] == "100"
    assert packages["p300"]["bonus_credits"] == "50"
    assert packages["p300"]["total_credits"] == "350"
    assert packages["p500"]["bonus_credits"] == "100"
    assert packages["p500"]["total_credits"] == "600"
    assert packages["p1000"]["bonus_credits"] == "150"
    assert packages["p1000"]["total_credits"] == "1150"
    assert packages["p2000"]["bonus_credits"] == "200"
    assert packages["p2000"]["total_credits"] == "2200"
    assert packages["p5000"]["bonus_credits"] == "500"
    assert packages["p5000"]["total_credits"] == "5500"


@pytest.mark.asyncio
async def test_successful_card_payment_credits_paid_rox_plus_bonus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"p300":{"credits":"300","prices":{"RUB":"326.1"},"dynamic_amount":true}}',
    )
    monkeypatch.setattr(settings, "card_offer_id", "offer-bonus")
    seen: dict[str, object] = {}

    async def fake_get_products(self: CardCheckoutClient) -> dict[str, object]:
        return {
            "items": [
                {
                    "id": "product-bonus",
                    "offers": [{"id": "offer-bonus", "isDynamicPrice": True}],
                }
            ]
        }

    async def fake_create_invoice(
        self: CardCheckoutClient,
        *,
        email: str,
        offer_id: str,
        currency: str,
        amount: Decimal | None,
        payment_provider: str | None = None,
    ) -> CreatedPayment:
        seen["invoice"] = {
            "email": email,
            "offer_id": offer_id,
            "currency": currency,
            "amount": amount,
            "payment_provider": payment_provider,
        }
        return CreatedPayment(
            external_id="card-bonus-1",
            payment_url="https://pay.example/bonus",
            raw={"status": "pending"},
        )

    async def fake_accrue_from_payment(
        session,
        *,
        source_user_id,
        source_transaction_id,
        payment_amount: Decimal,
    ) -> None:
        seen["referral_basis"] = payment_amount

    monkeypatch.setattr(CardCheckoutClient, "get_products", fake_get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", fake_create_invoice)
    monkeypatch.setattr(ReferralService, "accrue_from_payment", fake_accrue_from_payment)

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="ROX Bonus")
        session.add(user)
        await session.commit()

        payment = await CardPaymentService.create(
            session,
            user_id=user.id,
            package_id="p300",
            currency="RUB",
            billing_email="buyer@example.com",
            request_key=str(uuid.uuid4()),
        )

        assert seen["invoice"] == {
            "email": "buyer@example.com",
            "offer_id": "offer-bonus",
            "currency": "RUB",
            "amount": Decimal("326.1"),
            "payment_provider": None,
        }
        assert Decimal(payment.amount) == Decimal("326.1")
        assert Decimal(payment.rox_amount) == Decimal("350")
        assert payment.payload["base_credits"] == "300"
        assert payment.payload["bonus_credits"] == "50"
        assert payment.payload["credited_credits"] == "350"

        await CardPaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "paid"},
        )

        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("350.00")
        assert seen["referral_basis"] == Decimal("300")


@pytest.mark.asyncio
async def test_fixed_price_card_package_omits_amount_on_invoice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lava rejects `amount` for fixed-price offers (HTTP 400 "is not dynamic price").

    Regression: fixed-price card packages must create invoices without an amount,
    otherwise every checkout fails with 502 upstream.
    """
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"p300":{"credits":"300","prices":{"RUB":"326.1"}}}',
    )
    monkeypatch.setattr(settings, "card_offer_id", "offer-fixed")
    seen: dict[str, object] = {}

    async def fake_get_products(self: CardCheckoutClient) -> dict[str, object]:
        return {
            "items": [
                {
                    "id": "product-fixed",
                    "offers": [{"id": "offer-fixed", "name": "Fixed 300 ROX"}],
                }
            ]
        }

    async def fake_create_invoice(
        self: CardCheckoutClient,
        *,
        email: str,
        offer_id: str,
        currency: str,
        amount: Decimal | None,
        payment_provider: str | None = None,
    ) -> CreatedPayment:
        seen["invoice"] = {
            "email": email,
            "offer_id": offer_id,
            "currency": currency,
            "amount": amount,
            "payment_provider": payment_provider,
        }
        return CreatedPayment(
            external_id="card-fixed-1",
            payment_url="https://pay.example/fixed",
            raw={"status": "pending"},
        )

    monkeypatch.setattr(CardCheckoutClient, "get_products", fake_get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", fake_create_invoice)

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="ROX Fixed")
        session.add(user)
        await session.commit()

        payment = await CardPaymentService.create(
            session,
            user_id=user.id,
            package_id="p300",
            currency="RUB",
            billing_email="buyer@example.com",
            request_key=str(uuid.uuid4()),
        )

    assert seen["invoice"] == {
        "email": "buyer@example.com",
        "offer_id": "offer-fixed",
        "currency": "RUB",
        "amount": None,
        "payment_provider": None,
    }
    assert Decimal(payment.amount) == Decimal("326.1")


@pytest.mark.asyncio
async def test_lava_product_id_is_resolved_to_dynamic_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "card_offer_id", "product-1")

    async def fake_get_products(self: CardCheckoutClient) -> dict[str, object]:
        return {
            "items": [
                {
                    "id": "product-1",
                    "offers": [
                        {"id": "static-offer", "name": "Fixed 100 ROX"},
                        {"id": "dynamic-offer", "isDynamicPrice": True},
                    ],
                }
            ]
        }

    monkeypatch.setattr(CardCheckoutClient, "get_products", fake_get_products)
    client = CardCheckoutClient("api-key", "https://example.invalid")
    try:
        resolved = await CardPackageCatalog.resolve_invoice_offer(
            client,
            CardPackage(
                package_id="p100",
                credits=Decimal("100"),
                prices={"RUB": Decimal("108.7")},
            ),
        )
    finally:
        await client.aclose()

    assert resolved.offer_id == "dynamic-offer"
    assert resolved.source == "product_dynamic_offer"


def test_card_checkout_response_accepts_lava_payment_url_aliases() -> None:
    data = CardCheckoutClient._unwrap(
        {"data": {"contractId": "contract-1", "redirectUrl": "https://pay.example/1"}}
    )

    assert CardCheckoutClient.extract_invoice_id(data) == "contract-1"
    assert CardCheckoutClient.extract_payment_url(data) == "https://pay.example/1"


def test_top_up_bonus_catalog_matches_public_promo() -> None:
    assert TopUpBonusService.bonus_for(100) == Decimal("0")
    assert TopUpBonusService.bonus_for(300) == Decimal("50")
    assert TopUpBonusService.bonus_for(500) == Decimal("100")
    assert TopUpBonusService.bonus_for(1000) == Decimal("150")
    assert TopUpBonusService.bonus_for(2000) == Decimal("200")
    assert TopUpBonusService.bonus_for(5000) == Decimal("500")


def test_wallet_bonus_badges_are_backend_driven_in_mini_app() -> None:
    layout = (FRONTEND / "app" / "layout.tsx").read_text(encoding="utf-8")
    page = (FRONTEND / "app" / "page.tsx").read_text(encoding="utf-8")
    css = (FRONTEND / "app" / "wallet-bonuses.css").read_text(encoding="utf-8")
    wallet = (FRONTEND / "components" / "wallet-parity.tsx").read_text(encoding="utf-8")

    assert 'import "./wallet-bonuses.css";' in layout
    assert 'import { WalletParity } from "@/components/wallet-parity";' in page
    assert "<WalletParity />" in page
    assert 'customerRequest<PackageCatalog>("/api/v1/payments/card/packages")' in wallet
    assert "bonus_credits" in wallet
    assert "package-bonus-live" in wallet
    assert ".package-bonus-live" in css
    assert ":nth-child(" not in css
    for token in (
        "+50 ROX 🎁",
        "+100 ROX 🎁",
        "+150 ROX 🎁",
        "+200 ROX 🎁",
        "+500 ROX 🎁",
    ):
        assert token not in css
