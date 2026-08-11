import random
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Wallet
from app.db.session import SessionFactory
from app.services.wallet import InsufficientBalanceError, WalletService


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
            idempotency_key=f"credit:{user.id}",
        )
        duplicate = await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("100"),
            kind="test_credit",
            idempotency_key=f"credit:{user.id}",
        )
        assert duplicate.id == first.id

        await WalletService.debit(
            session,
            user_id=user.id,
            amount=Decimal("35"),
            kind="test_debit",
            idempotency_key=f"debit:{user.id}",
        )
        await session.commit()

        wallet = await session.get(Wallet, user.id)
        assert wallet is not None
        assert wallet.balance == Decimal("65.00")


@pytest.mark.asyncio
async def test_wallet_rejects_overdraft() -> None:
    async with SessionFactory() as session:
        user = User(telegram_id=random.randint(100_000_000_000, 999_999_999_999), first_name="CI")
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
