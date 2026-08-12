import random
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import Payment, ReferralReward, ReferralRelation, User, Wallet
from app.db.payment_models import PaymentRequest, PaymentReversal, ReferralRewardReversal
from app.db.session import SessionFactory
from app.providers.payments import CreatedPayment
from app.services.payments import PaymentIdempotencyConflict, PaymentService
from app.services.wallet import WalletService


def _telegram_id(prefix: int) -> int:
    return prefix * 1_000_000_000_000 + random.randint(1, 999_999_999)


@pytest.mark.asyncio
async def test_payment_creation_idempotency_prevents_duplicate_provider_invoice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"starter":{"credits":"30","currency":"RUB"}}',
    )
    calls: list[str] = []

    async def fake_create_external(
        provider: str,
        *,
        local_id: str,
        package: object,
        description: str,
    ) -> CreatedPayment:
        calls.append(local_id)
        return CreatedPayment(
            external_id="provider-1",
            payment_url="https://example.invalid/pay",
            raw={"provider": provider, "description": description, "package": str(package)},
        )

    monkeypatch.setattr(PaymentService, "_create_external", fake_create_external)
    request_key = str(uuid.uuid4())

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(5), first_name="PayIdempotent")
        session.add(user)
        await session.commit()

        first = await PaymentService.create(
            session,
            user_id=user.id,
            provider="yookassa",
            package_id="starter",
            request_key=request_key,
        )
        second = await PaymentService.create(
            session,
            user_id=user.id,
            provider="yookassa",
            package_id="starter",
            request_key=request_key,
        )

        assert first.id == second.id
        assert calls == [str(first.id)]
        request_row = await session.scalar(
            select(PaymentRequest).where(
                PaymentRequest.user_id == user.id,
                PaymentRequest.request_key == request_key,
            )
        )
        assert request_row is not None
        assert request_row.status == "completed"


@pytest.mark.asyncio
async def test_payment_idempotency_key_cannot_be_reused_for_another_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "rox_packages_json",
        '{"a":{"credits":"10","currency":"RUB"},"b":{"credits":"20","currency":"RUB"}}',
    )

    async def fake_create_external(
        provider: str,
        *,
        local_id: str,
        package: object,
        description: str,
    ) -> CreatedPayment:
        return CreatedPayment("provider-conflict", "https://example.invalid/pay", {})

    monkeypatch.setattr(PaymentService, "_create_external", fake_create_external)
    request_key = str(uuid.uuid4())

    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(6), first_name="PayConflict")
        session.add(user)
        await session.commit()
        await PaymentService.create(
            session,
            user_id=user.id,
            provider="tbank",
            package_id="a",
            request_key=request_key,
        )
        with pytest.raises(PaymentIdempotencyConflict):
            await PaymentService.create(
                session,
                user_id=user.id,
                provider="tbank",
                package_id="b",
                request_key=request_key,
            )


@pytest.mark.asyncio
async def test_full_reversal_is_idempotent_and_can_create_accounting_debt() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(7), first_name="RefundDebt")
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)
        payment = Payment(
            user_id=user.id,
            provider="yookassa",
            external_id=f"yk-{uuid.uuid4()}",
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
        await WalletService.debit(
            session,
            user_id=user.id,
            amount=Decimal("25"),
            kind="test_spend",
            idempotency_key=f"test-spend:{payment.id}",
        )
        await session.commit()

        key = f"test-reversal:{payment.id}"
        await PaymentService.apply_reversal(
            session,
            payment_id=payment.id,
            amount=Decimal("300"),
            provider="yookassa",
            idempotency_key=key,
            reason="refund",
            provider_payload={"status": "succeeded"},
        )
        await PaymentService.apply_reversal(
            session,
            payment_id=payment.id,
            amount=Decimal("300"),
            provider="yookassa",
            idempotency_key=key,
            reason="refund",
            provider_payload={"status": "succeeded"},
        )

        wallet = await session.get(Wallet, user.id)
        refreshed = await session.get(Payment, payment.id)
        reversal_count = await session.scalar(
            select(func.count()).select_from(PaymentReversal).where(
                PaymentReversal.payment_id == payment.id
            )
        )
        assert wallet is not None
        assert wallet.balance == Decimal("-25.00")
        assert refreshed is not None and refreshed.status == "refunded"
        assert reversal_count == 1


@pytest.mark.asyncio
async def test_yookassa_cumulative_refunded_amount_drives_partial_then_full_reversal() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(8), first_name="YooRefund")
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)
        payment = Payment(
            user_id=user.id,
            provider="yookassa",
            external_id=f"yk-{uuid.uuid4()}",
            amount=Decimal("300"),
            currency="RUB",
            rox_amount=Decimal("30"),
            status="pending",
            payload={},
        )
        session.add(payment)
        await session.commit()

        base = {
            "id": str(payment.external_id),
            "status": "succeeded",
            "amount": {"value": "300.00", "currency": "RUB"},
            "metadata": {"payment_id": str(payment.id)},
        }
        first_state = {
            **base,
            "refunded_amount": {"value": "100.00", "currency": "RUB"},
        }
        await PaymentService.apply_yookassa_state(session, payment.id, first_state)
        wallet = await session.get(Wallet, user.id)
        first_payment = await session.get(Payment, payment.id)
        assert wallet is not None and wallet.balance == Decimal("20.00")
        assert first_payment is not None and first_payment.status == "partially_refunded"

        full_state = {
            **base,
            "refunded_amount": {"value": "300.00", "currency": "RUB"},
        }
        await PaymentService.apply_yookassa_state(session, payment.id, full_state)
        await PaymentService.apply_yookassa_state(session, payment.id, full_state)
        wallet = await session.get(Wallet, user.id)
        full_payment = await session.get(Payment, payment.id)
        total = await session.scalar(
            select(func.coalesce(func.sum(PaymentReversal.amount), 0)).where(
                PaymentReversal.payment_id == payment.id
            )
        )
        assert wallet is not None and wallet.balance == Decimal("0.00")
        assert full_payment is not None and full_payment.status == "refunded"
        assert Decimal(total or 0) == Decimal("300.00")


@pytest.mark.asyncio
async def test_referral_rewards_are_reversed_proportionally() -> None:
    async with SessionFactory() as session:
        inviter = User(telegram_id=_telegram_id(9), first_name="Inviter")
        buyer = User(telegram_id=_telegram_id(10), first_name="Buyer")
        session.add_all([inviter, buyer])
        await session.flush()
        session.add(
            ReferralRelation(referred_user_id=buyer.id, inviter_user_id=inviter.id)
        )
        await WalletService.ensure_wallet(session, buyer.id)
        payment = Payment(
            user_id=buyer.id,
            provider="yookassa",
            external_id=f"yk-{uuid.uuid4()}",
            amount=Decimal("300"),
            currency="RUB",
            rox_amount=Decimal("30"),
            status="pending",
            payload={},
        )
        session.add(payment)
        await session.commit()

        await PaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "succeeded"},
        )
        reward = await session.scalar(
            select(ReferralReward).where(
                ReferralReward.partner_user_id == inviter.id,
                ReferralReward.source_user_id == buyer.id,
            )
        )
        assert reward is not None and reward.amount == Decimal("90.00")

        await PaymentService.apply_reversal(
            session,
            payment_id=payment.id,
            amount=Decimal("150"),
            provider="yookassa",
            idempotency_key=f"partial:{payment.id}",
            reason="partial_refund",
            provider_payload={},
        )
        reversed_reward = await session.scalar(
            select(func.coalesce(func.sum(ReferralRewardReversal.amount), 0)).where(
                ReferralRewardReversal.reward_id == reward.id
            )
        )
        assert Decimal(reversed_reward or 0) == Decimal("45.00")


@pytest.mark.asyncio
async def test_tbank_full_refunded_state_reverses_credited_payment() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=_telegram_id(11), first_name="TBankRefund")
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
                "Status": "REFUNDED",
                "Amount": 30000,
            },
        )
        wallet = await session.get(Wallet, user.id)
        refreshed = await session.get(Payment, payment.id)
        assert wallet is not None and wallet.balance == Decimal("0.00")
        assert refreshed is not None and refreshed.status == "refunded"
