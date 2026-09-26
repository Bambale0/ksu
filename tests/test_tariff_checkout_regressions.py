import asyncio
import json
import random
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.db.admin_models import AdminCommand, TariffVersion
from app.db.models import AdminAccount, User
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import CreatedPayment
from app.services.admin_pricing import AdminPricingService, TariffValidationError
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


@pytest.mark.asyncio
async def test_text_admin_model_price_patch_preserves_other_tariff_data(monkeypatch):
    for field in ("rox_packages_json", "generation_pricing_json", "music_generation_price_rox"):
        monkeypatch.setattr(settings, field, getattr(settings, field))

    async with SessionFactory() as session:
        user = User(telegram_id=random.randint(890_000_000_000, 899_999_999_999))
        session.add(user)
        await session.flush()
        admin = AdminAccount(user_id=user.id, role="admin", is_active=True, mfa_enabled=True)
        session.add(admin)
        await session.flush()

        packages = {
            "review": {
                "amount": "321",
                "credits": "300",
                "bonus_credits": "37",
                "currency": "RUB",
            }
        }
        initial_pricing = {
            "nano-banana-2": {"flat": "27"},
            "kling-motion-3.0": {
                "per_second": "65",
                "by_mode": {"720p": "65", "1080p": "85"},
            },
        }
        await AdminPricingService.publish(
            session,
            admin=admin,
            payload={"packages": packages, "generation_pricing": initial_pricing},
            idempotency_key=f"tariff-model-seed:{uuid.uuid4()}",
            request_id="tariff-model-seed",
            confirmed=True,
            step_up_valid=True,
        )

        result, replayed = await AdminPricingService.publish_model_price(
            session,
            admin=admin,
            model_id="nano-banana-2",
            price=Decimal("33.5"),
            idempotency_key=f"tariff-model-price:{uuid.uuid4()}",
            request_id="tariff-model-price",
            confirmed=True,
            step_up_valid=True,
        )

        assert replayed is False
        saved = await AdminPricingService.get_version(
            session,
            admin=admin,
            version_id=uuid.UUID(result["id"]),
        )
        assert saved["payload"]["packages"] == packages
        assert saved["payload"]["generation_pricing"]["nano-banana-2"]["flat"] == "33.5"
        assert saved["payload"]["generation_pricing"]["kling-motion-3.0"] == initial_pricing["kling-motion-3.0"]
        assert json.loads(settings.generation_pricing_json)["nano-banana-2"]["flat"] == "33.5"

        second, _ = await AdminPricingService.publish_model_price(
            session,
            admin=admin,
            model_id="kling-motion-3.0",
            price=Decimal("70"),
            idempotency_key=f"tariff-model-price:{uuid.uuid4()}",
            request_id="tariff-model-price-tier-preserve",
            confirmed=True,
            step_up_valid=True,
        )
        second_saved = await AdminPricingService.get_version(
            session,
            admin=admin,
            version_id=uuid.UUID(second["id"]),
        )
        assert second_saved["payload"]["generation_pricing"]["kling-motion-3.0"] == {
            "per_second": "70",
            "by_mode": {"720p": "65", "1080p": "85"},
        }
        assert second_saved["payload"]["generation_pricing"]["nano-banana-2"]["flat"] == "33.5"
        assert second_saved["payload"]["packages"] == packages

        with pytest.raises(TariffValidationError, match="positive"):
            await AdminPricingService.publish_model_price(
                session,
                admin=admin,
                model_id="nano-banana-2",
                price="NaN",
                idempotency_key=f"tariff-model-price:{uuid.uuid4()}",
                request_id="tariff-model-price-nan",
                confirmed=True,
                step_up_valid=True,
            )

        await session.rollback()


@pytest.mark.asyncio
async def test_concurrent_model_price_edits_preserve_both_updates(monkeypatch):
    for field in ("rox_packages_json", "generation_pricing_json", "music_generation_price_rox"):
        monkeypatch.setattr(settings, field, getattr(settings, field))

    async with SessionFactory() as setup:
        published_before = list(
            (
                await setup.scalars(
                    select(TariffVersion.id).where(TariffVersion.status == "published")
                )
            ).all()
        )
        user = User(telegram_id=random.randint(900_000_000_000, 909_999_999_999))
        setup.add(user)
        await setup.flush()
        user_id = user.id
        admin = AdminAccount(user_id=user.id, role="admin", is_active=True, mfa_enabled=True)
        setup.add(admin)
        await setup.flush()
        admin_id = admin.id
        await AdminPricingService.publish(
            setup,
            admin=admin,
            payload={
                "generation_pricing": {
                    "nano-banana-2": {"flat": "27"},
                    "kling-motion-3.0": {
                        "per_second": "65",
                        "by_mode": {"720p": "65", "1080p": "85"},
                    },
                }
            },
            idempotency_key=f"tariff-concurrency-seed:{uuid.uuid4()}",
            request_id="tariff-concurrency-seed",
            confirmed=True,
            step_up_valid=True,
        )
        await setup.commit()

    async def publish_one(model_id: str, price: str) -> None:
        async with SessionFactory() as session:
            admin = await session.get(AdminAccount, admin_id)
            assert admin is not None
            await AdminPricingService.publish_model_price(
                session,
                admin=admin,
                model_id=model_id,
                price=price,
                idempotency_key=f"tariff-concurrency:{model_id}:{uuid.uuid4()}",
                request_id=f"tariff-concurrency:{model_id}",
                confirmed=True,
                step_up_valid=True,
            )
            await session.commit()

    try:
        await asyncio.gather(
            publish_one("nano-banana-2", "34"),
            publish_one("kling-motion-3.0", "71"),
        )

        async with SessionFactory() as verify:
            admin = await verify.get(AdminAccount, admin_id)
            assert admin is not None
            current = await AdminPricingService.current(verify, admin=admin)
            assert current is not None
            pricing = current["payload"]["generation_pricing"]
            assert pricing["nano-banana-2"]["flat"] == "34"
            assert pricing["kling-motion-3.0"] == {
                "per_second": "71",
                "by_mode": {"720p": "65", "1080p": "85"},
            }
    finally:
        async with SessionFactory() as cleanup:
            await cleanup.execute(
                delete(AdminCommand).where(AdminCommand.admin_user_id == admin_id)
            )
            await cleanup.execute(
                delete(TariffVersion).where(TariffVersion.created_by_admin_id == admin_id)
            )
            if published_before:
                await cleanup.execute(
                    update(TariffVersion)
                    .where(TariffVersion.id.in_(published_before))
                    .values(status="published")
                )
            await cleanup.execute(delete(AdminAccount).where(AdminAccount.id == admin_id))
            await cleanup.execute(delete(User).where(User.id == user_id))
            await cleanup.commit()
