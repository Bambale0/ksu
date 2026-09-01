from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import User, Wallet
from app.db.session import SessionFactory
from app.providers.payments import CreatedPayment
from app.services.payments import PaymentService
from app.services.yookassa_payments import YooKassaPaymentService


def _telegram_id() -> int:
    return 99_800_000_000_000 + random.randint(1, 999_999_999)


@pytest.mark.asyncio
async def test_yookassa_payment_credits_base_rox_plus_package_bonus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"p300":{"credits":"300","amount":"300","currency":"RUB"}}',
    )

    async def fake_create_external(
        provider: str,
        *,
        local_id: str,
        package: object,
        description: str,
    ) -> CreatedPayment:
        assert provider == "yookassa"
        return CreatedPayment(
            external_id=f"yookassa-bonus-{uuid.uuid4()}",
            payment_url="https://pay.example/yookassa-bonus",
            raw={"status": "pending", "description": description, "local_id": local_id},
        )

    monkeypatch.setattr(PaymentService, "_create_external", fake_create_external)

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Yoo Bonus")
        session.add(user)
        await session.commit()

        payment = await YooKassaPaymentService.create(
            session,
            user_id=user.id,
            package_id="p300",
            request_key=str(uuid.uuid4()),
        )

        assert Decimal(payment.amount) == Decimal("300")
        assert Decimal(payment.rox_amount) == Decimal("350")
        assert payment.payload["base_credits"] == "300"
        assert payment.payload["bonus_credits"] == "50"
        assert payment.payload["credited_credits"] == "350"

        await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded"},
        )
        await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded", "duplicate": True},
        )

        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("350.00")
