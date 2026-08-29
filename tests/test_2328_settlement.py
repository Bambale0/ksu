from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest

from app.db.models import Payment, User, Wallet
from app.db.session import SessionFactory
from app.services.payment_2328 import Payment2328Service
from app.services.wallet import WalletService


def _telegram_id() -> int:
    return 9_820_000_000_000 + random.randint(1, 999_999_999)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_status", ["paid", "overpaid"])
async def test_2328_success_state_credits_wallet_once(provider_status: str) -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(), first_name="Settlement2328")
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)

        payment = Payment(
            user_id=user.id,
            provider=Payment2328Service.PROVIDER,
            external_id=f"2328-{uuid.uuid4()}",
            amount=Decimal("300.00"),
            currency="RUB",
            rox_amount=Decimal("350.00"),
            status="pending",
            payload={"package_id": "starter"},
        )
        session.add(payment)
        await session.commit()

        state = {
            "uuid": payment.external_id,
            "order_id": str(payment.id),
            "amount": "300.00000000",
            "currency": "RUB",
            "payment_status": provider_status,
            "payment_amount": "1.23456789" if provider_status == "overpaid" else "1.00000000",
            "merchant_amount": "1.220000000000000000",
        }

        await Payment2328Service.apply_state(session, payment=payment, provider_payload=state)
        await Payment2328Service.apply_state(session, payment=payment, provider_payload=state)

        wallet = await session.get(Wallet, user.id)
        refreshed = await session.get(Payment, payment.id)
        assert wallet is not None
        assert wallet.balance == Decimal("350.00")
        assert refreshed is not None
        assert refreshed.status == "succeeded"
        assert refreshed.payload["last_provider_state"]["payment_status"] == provider_status
