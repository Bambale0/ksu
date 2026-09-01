from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PartnerWithdrawal, User
from app.db.partner_wallet_models import PartnerWalletTransfer
from app.services.credits import InternalCreditService
from app.services.partner import PartnerService, PartnerWithdrawalError
from app.services.wallet import WalletService


class PartnerWalletTransferError(ValueError):
    pass


class PartnerWalletTransferInsufficientFunds(PartnerWalletTransferError):
    pass


class PartnerWalletTransferIdempotencyConflict(PartnerWalletTransferError):
    pass


class PartnerWalletTransferService:
    @staticmethod
    async def transferred_total(session: AsyncSession, user_id: uuid.UUID) -> Decimal:
        return Decimal(
            (
                await session.scalar(
                    select(func.coalesce(func.sum(PartnerWalletTransfer.amount_rub), 0)).where(
                        PartnerWalletTransfer.user_id == user_id
                    )
                )
            )
            or 0
        )

    @classmethod
    async def accounting(cls, session: AsyncSession, user_id: uuid.UUID) -> dict[str, Decimal]:
        # PartnerService is the single source of truth for the shared RUB earnings
        # pool. It already subtracts both cash withdrawals and RUB->ROX transfers.
        return await PartnerService.accounting(session, user_id)

    @staticmethod
    async def _lock_user(session: AsyncSession, user_id: uuid.UUID) -> User:
        user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
        if user is None:
            raise LookupError("User not found")
        return user

    @staticmethod
    def _validate_replay(existing: PartnerWalletTransfer, amount: Decimal) -> None:
        if Decimal(existing.amount_rub) != amount:
            raise PartnerWalletTransferIdempotencyConflict(
                "Idempotency key was already used for another transfer amount"
            )

    @classmethod
    async def assert_available(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        lock: bool = False,
    ) -> dict[str, Decimal]:
        normalized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if normalized <= 0:
            raise PartnerWalletTransferError("Amount must be positive")
        if lock:
            await cls._lock_user(session, user_id)
        accounting = await cls.accounting(session, user_id)
        if normalized > accounting["available"]:
            raise PartnerWalletTransferInsufficientFunds(
                "Amount exceeds available partner earnings"
            )
        return accounting

    @classmethod
    async def transfer(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        idempotency_key: str,
    ) -> PartnerWalletTransfer:
        key = idempotency_key.strip()
        if not key:
            raise PartnerWalletTransferError("Idempotency key is required")
        normalized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if normalized <= 0:
            raise PartnerWalletTransferError("Amount must be positive")

        existing = await session.scalar(
            select(PartnerWalletTransfer).where(
                PartnerWalletTransfer.idempotency_key == key,
                PartnerWalletTransfer.user_id == user_id,
            )
        )
        if existing is not None:
            cls._validate_replay(existing, normalized)
            return existing

        await cls._lock_user(session, user_id)

        # Re-check after the per-user row lock. This makes retries safe even when two
        # identical requests arrive concurrently before either transfer is committed.
        existing = await session.scalar(
            select(PartnerWalletTransfer).where(
                PartnerWalletTransfer.idempotency_key == key,
                PartnerWalletTransfer.user_id == user_id,
            )
        )
        if existing is not None:
            cls._validate_replay(existing, normalized)
            return existing
        await cls.assert_available(
            session,
            user_id=user_id,
            amount=normalized,
            lock=False,
        )

        transfer_id = uuid.uuid4()
        rox_amount = InternalCreditService.credits_for(normalized)
        wallet_tx = await WalletService.credit(
            session,
            user_id=user_id,
            amount=rox_amount,
            kind="partner_earnings_transfer",
            reference_type="partner_wallet_transfer",
            reference_id=str(transfer_id),
            idempotency_key=f"partner-wallet:{user_id}:{key}",
        )
        transfer = PartnerWalletTransfer(
            id=transfer_id,
            user_id=user_id,
            amount_rub=normalized,
            rox_amount=rox_amount,
            wallet_transaction_id=wallet_tx.id,
            idempotency_key=key,
        )
        session.add(transfer)
        await session.flush()
        return transfer

    @classmethod
    async def create_cash_withdrawal(
        cls,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        amount: Decimal,
        requisites: str,
        idempotency_key: str,
    ) -> PartnerWithdrawal:
        """Serialize cash withdrawal with RUB->ROX conversion and safe request replay."""

        key = idempotency_key.strip()
        if not key or len(key) > 160:
            raise PartnerWithdrawalError("Valid Idempotency-Key is required")
        normalized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cleaned = requisites.strip()

        replay = await PartnerService._withdrawal_replay(
            session,
            user_id=user_id,
            key=key,
            amount=normalized,
            requisites=cleaned,
        )
        if replay is not None:
            return replay

        await cls._lock_user(session, user_id)
        replay = await PartnerService._withdrawal_replay(
            session,
            user_id=user_id,
            key=key,
            amount=normalized,
            requisites=cleaned,
        )
        if replay is not None:
            return replay

        await cls.assert_available(
            session,
            user_id=user_id,
            amount=normalized,
            lock=False,
        )
        return await PartnerService.create_withdrawal(
            session,
            user_id=user_id,
            amount=normalized,
            requisites=cleaned,
            idempotency_key=key,
        )
