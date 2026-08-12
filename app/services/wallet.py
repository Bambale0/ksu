import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Wallet, WalletTransaction


class InsufficientBalanceError(ValueError):
    pass


class WalletService:
    @staticmethod
    async def ensure_wallet(session: AsyncSession, user_id: uuid.UUID) -> Wallet:
        wallet = await session.get(Wallet, user_id)
        if wallet is None:
            wallet = Wallet(user_id=user_id, balance=Decimal("0"))
            session.add(wallet)
            await session.flush()
        return wallet

    @staticmethod
    async def _existing_by_key(
        session: AsyncSession, idempotency_key: str | None
    ) -> WalletTransaction | None:
        if not idempotency_key:
            return None
        return await session.scalar(
            select(WalletTransaction).where(
                WalletTransaction.idempotency_key == idempotency_key
            )
        )

    @classmethod
    async def credit(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        kind: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> WalletTransaction:
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        existing = await cls._existing_by_key(session, idempotency_key)
        if existing:
            return existing

        wallet = await session.scalar(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        if wallet is None:
            wallet = Wallet(user_id=user_id, balance=Decimal("0"))
            session.add(wallet)
            await session.flush()

        before = Decimal(wallet.balance)
        after = before + amount
        wallet.balance = after
        tx = WalletTransaction(
            user_id=user_id,
            kind=kind,
            amount=amount,
            balance_before=before,
            balance_after=after,
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
        )
        session.add(tx)
        await session.flush()
        return tx

    @classmethod
    async def debit(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        kind: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> WalletTransaction:
        return await cls._debit(
            session,
            user_id=user_id,
            amount=amount,
            kind=kind,
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            allow_negative=False,
        )

    @classmethod
    async def accounting_debit(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        kind: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> WalletTransaction:
        """Debit an external-accounting reversal even if credits were already spent.

        A provider refund/chargeback must be represented faithfully. Allowing a
        negative balance prevents the system from silently keeping refunded credits;
        normal user debits still reject insufficient balance.
        """

        return await cls._debit(
            session,
            user_id=user_id,
            amount=amount,
            kind=kind,
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
            allow_negative=True,
        )

    @classmethod
    async def _debit(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        kind: str,
        reference_type: str | None,
        reference_id: str | None,
        idempotency_key: str | None,
        allow_negative: bool,
    ) -> WalletTransaction:
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        existing = await cls._existing_by_key(session, idempotency_key)
        if existing:
            return existing

        wallet = await session.scalar(
            select(Wallet).where(Wallet.user_id == user_id).with_for_update()
        )
        if wallet is None:
            wallet = Wallet(user_id=user_id, balance=Decimal("0"))
            session.add(wallet)
            await session.flush()
        if not allow_negative and Decimal(wallet.balance) < amount:
            raise InsufficientBalanceError("Not enough ROX")

        before = Decimal(wallet.balance)
        after = before - amount
        wallet.balance = after
        tx = WalletTransaction(
            user_id=user_id,
            kind=kind,
            amount=-amount,
            balance_before=before,
            balance_after=after,
            reference_type=reference_type,
            reference_id=reference_id,
            idempotency_key=idempotency_key,
        )
        session.add(tx)
        await session.flush()
        return tx
