import random
import uuid
from decimal import Decimal

import pytest

from app.db.models import Payment, User, Wallet
from app.db.session import SessionFactory
from app.services.payment_refunds import PaymentRefundService
from app.services.wallet import WalletService


@pytest.mark.asyncio
async def test_tbank_full_admin_refund_calls_cancel_and_reverses_credits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class FakeTBankClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def refund_full(self, *, external_id: str, request_key: str) -> dict[str, object]:
            calls.append((external_id, request_key))
            return {
                "Success": True,
                "PaymentId": external_id,
                "Status": "REFUNDED",
                "Amount": 30000,
            }

    monkeypatch.setattr("app.services.payment_refunds.TBankClient", FakeTBankClient)

    async with SessionFactory() as session:
        user = User(
            telegram_id=12_000_000_000_000 + random.randint(1, 999_999_999),
            first_name="TBankCancel",
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

        request_key = str(uuid.uuid4())
        refund = await PaymentRefundService.initiate(
            session,
            payment_id=payment.id,
            amount=Decimal("300"),
            request_key=request_key,
            reason="Full customer refund",
        )
        duplicate = await PaymentRefundService.initiate(
            session,
            payment_id=payment.id,
            amount=Decimal("300"),
            request_key=request_key,
            reason="Full customer refund",
        )

        wallet = await session.get(Wallet, user.id)
        refreshed = await session.get(Payment, payment.id)
        assert calls == [(str(payment.external_id), request_key)]
        assert duplicate.id == refund.id
        assert refund.provider == "tbank"
        assert wallet is not None and wallet.balance == Decimal("0.00")
        assert refreshed is not None and refreshed.status == "refunded"
