import random
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db.models import Payment, User, Wallet
from app.db.payment_models import PaymentReversal
from app.db.session import SessionFactory
from app.services.payments import PaymentService
from app.services.wallet import WalletService


@pytest.mark.asyncio
async def test_partial_tbank_refund_state_never_guesses_reversal_amount() -> None:
    async with SessionFactory() as session:
        user = User(
            telegram_id=13_000_000_000_000 + random.randint(1, 999_999_999),
            first_name="TBankPartial",
        )
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)
        payment = Payment(
            user_id=user.id,
            provider="tbank",
            external_id=str(random.randint(10_000_000, 99_999_999)),
            amount=Decimal("300"),
            currency="RUB",
            rox_amount=Decimal("30"),
            status="succeeded",
            payload={},
        )
        session.add(payment)
        await session.flush()
        await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("30"),
            kind="payment",
            reference_type="payment",
            reference_id=str(payment.id),
            idempotency_key=f"payment:{payment.id}:credit",
        )
        await session.commit()

        await PaymentService.apply_tbank_state(
            session,
            payment.id,
            {
                "PaymentId": str(payment.external_id),
                "Status": "PARTIAL_REFUNDED",
                "NotificationAmount": 10000,
            },
        )

        refreshed = await session.get(Payment, payment.id)
        wallet = await session.get(Wallet, user.id)
        reversals = await session.scalar(
            select(func.count()).select_from(PaymentReversal).where(
                PaymentReversal.payment_id == payment.id
            )
        )
        assert refreshed is not None and refreshed.status == "refund_review"
        assert wallet is not None and wallet.balance == Decimal("30.00")
        assert reversals == 0
