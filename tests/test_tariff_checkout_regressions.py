import json
import random
import uuid
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import AdminAccount, User
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import CreatedPayment
from app.services.admin_pricing import AdminPricingService
from app.services.card_payments import CardPackageCatalog, CardPaymentService
from app.services.payments import PaymentService


@pytest.mark.asyncio
async def test_partial_tariff_publish_and_old_retry_preserve_current_checkout_prices(monkeypatch):
    for field in ("rox_packages_json", "generation_pricing_json", "music_generation_price_rox"):
        monkeypatch.setattr(settings, field, getattr(settings, field))
    async with SessionFactory() as session:
        user = User(telegram_id=random.randint(880_000_000_000, 889_999_999_999))
        session.add(user)
        await session.flush()
        admin = AdminAccount(user_id=user.id, role="admin", is_active=True, mfa_enabled=True)
        session.add(admin)
        await session.flush()
        packages = {"review": {"amount": "321", "credits": "300", "bonus_credits": "37", "currency": "RUB"}}
        first_payload = {"packages": packages, "generation_pricing": {"nano-banana-2": {"flat": 27}}}
        key = f"tariff-regression:{uuid.uuid4()}"
        args = dict(admin=admin, request_id=key, confirmed=True, step_up_valid=True)
        await AdminPricingService.publish(session, payload=first_payload, idempotency_key=key, **args)
        second, _ = await AdminPricingService.publish(
            session, payload={"generation_pricing": {"nano-banana-2": {"flat": 31}}},
            idempotency_key=f"tariff-regression:{uuid.uuid4()}", **args,
        )
        saved = await AdminPricingService.get_version(session, admin=admin, version_id=uuid.UUID(second["id"]))
        assert saved["payload"]["packages"] == packages
        settings.rox_packages_json = "{}"
        await AdminPricingService.hydrate_runtime(session)
        assert PaymentService.package("review").amount == Decimal("321")
        _, replayed = await AdminPricingService.publish(session, payload=first_payload, idempotency_key=key, **args)
        assert replayed is True
        assert json.loads(settings.generation_pricing_json)["nano-banana-2"]["flat"] == 31
        await session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_dynamic", [False, True])
async def test_admin_tariff_keeps_card_offer_and_sends_authoritative_rub(monkeypatch, explicit_dynamic):
    monkeypatch.setattr(settings, "rox_packages_json", json.dumps({
        "review": {"amount": "321", "credits": "300", "bonus_credits": "37", "currency": "RUB"},
    }))
    monkeypatch.setattr(settings, "card_packages_json", json.dumps({
        "review": {"credits": "999", "prices": {"RUB": "900", "USD": "8"},
                   "offer_id": "review-offer", "dynamic_amount": explicit_dynamic},
    }))
    monkeypatch.setattr(settings, "card_offer_id", "wrong-global-offer")
    monkeypatch.setattr(settings, "card_payment_route_by_currency_json", "{}")
    seen = []

    async def products(self):
        return {"items": [{"id": "review-product", "offers": [
            {"id": "review-offer", "isDynamicPrice": not explicit_dynamic},
        ]}]}

    async def invoice(self, **kwargs):
        seen.append(kwargs)
        return CreatedPayment(external_id=f"review-{uuid.uuid4()}", payment_url="https://pay.example/test", raw={})

    monkeypatch.setattr(CardCheckoutClient, "get_products", products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", invoice)
    package = CardPackageCatalog.package("review")
    assert package.offer_id == "review-offer"
    assert package.prices == {"RUB": Decimal("321"), "USD": Decimal("8")}
    assert package.credits == Decimal("300")
    assert package.bonus_credits == Decimal("37")
    async with SessionFactory() as session:
        user = User(telegram_id=random.randint(880_000_000_000, 889_999_999_999))
        session.add(user)
        await session.flush()
        payment = await CardPaymentService.create(
            session, user_id=user.id, package_id="review", currency="RUB",
            billing_email="review@example.com", request_key=str(uuid.uuid4()),
        )
        assert seen[0]["offer_id"] == "review-offer"
        assert seen[0]["amount"] == Decimal("321")
        assert payment.amount == Decimal("321")
        assert payment.rox_amount == Decimal("300")
        assert payment.payload["promo_package_bonus_credits"] == "37"
