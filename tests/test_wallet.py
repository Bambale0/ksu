import random
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Wallet
from app.db.session import SessionFactory
from app.services.wallet import (
    IdempotencyConflictError,
    InsufficientBalanceError,
    WalletService,
)


@pytest.mark.asyncio
async def test_wallet_credit_debit_and_idempotency() -> None:
    async with SessionFactory() as session:
        assert isinstance(session, AsyncSession)
        user = User(telegram_id=random.randint(10_000_000_000, 99_999_999_999), first_name="CI")
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)

        first = await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("100"),
            kind="test_credit",
            reference_type="test",
            reference_id="credit-1",
            idempotency_key=f"credit:{user.id}",
        )
        duplicate = await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("100"),
            kind="test_credit",
            reference_type="test",
            reference_id="credit-1",
            idempotency_key=f"credit:{user.id}",
        )
        assert duplicate.id == first.id

        debit = await WalletService.debit(
            session,
            user_id=user.id,
            amount=Decimal("35"),
            kind="test_debit",
            reference_type="test",
            reference_id="debit-1",
            idempotency_key=f"debit:{user.id}",
        )
        debit_duplicate = await WalletService.debit(
            session,
            user_id=user.id,
            amount=Decimal("35"),
            kind="test_debit",
            reference_type="test",
            reference_id="debit-1",
            idempotency_key=f"debit:{user.id}",
        )
        assert debit_duplicate.id == debit.id
        await session.commit()

        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("65.00")


@pytest.mark.asyncio
async def test_wallet_rejects_conflicting_idempotency_replays() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=random.randint(100_000_000_000, 199_999_999_999), first_name="CI")
        other_user = User(
            telegram_id=random.randint(200_000_000_000, 299_999_999_999), first_name="CI"
        )
        session.add_all([user, other_user])
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)
        await WalletService.ensure_wallet(session, other_user.id)

        key = f"wallet-replay:{user.id}"
        first = await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("100"),
            kind="payment_credit",
            reference_type="payment",
            reference_id="payment-1",
            idempotency_key=key,
        )

        conflict_cases = [
            {
                "user_id": other_user.id,
                "amount": Decimal("100"),
                "kind": "payment_credit",
                "reference_type": "payment",
                "reference_id": "payment-1",
            },
            {
                "user_id": user.id,
                "amount": Decimal("101"),
                "kind": "payment_credit",
                "reference_type": "payment",
                "reference_id": "payment-1",
            },
            {
                "user_id": user.id,
                "amount": Decimal("100"),
                "kind": "bonus_credit",
                "reference_type": "payment",
                "reference_id": "payment-1",
            },
            {
                "user_id": user.id,
                "amount": Decimal("100"),
                "kind": "payment_credit",
                "reference_type": "payment",
                "reference_id": "payment-2",
            },
        ]
        for case in conflict_cases:
            with pytest.raises(IdempotencyConflictError):
                await WalletService.credit(session, idempotency_key=key, **case)

        with pytest.raises(IdempotencyConflictError):
            await WalletService.debit(
                session,
                user_id=user.id,
                amount=Decimal("100"),
                kind="payment_credit",
                reference_type="payment",
                reference_id="payment-1",
                idempotency_key=key,
            )

        assert first.amount == Decimal("100")
        assert (await session.get(Wallet, user.id)).balance == Decimal("100")
        assert (await session.get(Wallet, other_user.id)).balance == Decimal("0")
        await session.rollback()


@pytest.mark.asyncio
async def test_wallet_rejects_overdraft() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=random.randint(300_000_000_000, 399_999_999_999), first_name="CI")
        session.add(user)
        await session.flush()
        await WalletService.ensure_wallet(session, user.id)
        with pytest.raises(InsufficientBalanceError):
            await WalletService.debit(
                session,
                user_id=user.id,
                amount=Decimal("1"),
                kind="test_debit",
            )
        await session.rollback()
