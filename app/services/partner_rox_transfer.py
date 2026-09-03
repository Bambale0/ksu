from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Wallet, WalletTransaction
from app.services.wallet import WalletService


class PartnerRoxTransferError(ValueError):
    pass


class PartnerRoxRecipientNotAllowed(PartnerRoxTransferError):
    pass


@dataclass(frozen=True)
class PartnerRoxTransferResult:
    transfer_id: uuid.UUID
    recipient_user_id: uuid.UUID
    recipient_telegram_id: int
    sender_transaction: WalletTransaction
    recipient_transaction: WalletTransaction


class PartnerRoxTransferService:
    @staticmethod
    def _transfer_id(
        *,
        sender_user_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        idempotency_key: str,
    ) -> uuid.UUID:
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"roxy:partner-rox-transfer:{sender_user_id}:{recipient_user_id}:{idempotency_key}",
        )

    @staticmethod
    async def _recipient(
        session: AsyncSession,
        *,
        recipient_user_id: uuid.UUID | None,
        recipient_telegram_id: int | None,
    ) -> User:
        if recipient_user_id is not None and recipient_telegram_id is not None:
            raise PartnerRoxTransferError("Укажите только один ID получателя")
        if recipient_telegram_id is not None:
            if recipient_telegram_id <= 0:
                raise PartnerRoxTransferError("Некорректный ID пользователя")
            recipient = await session.scalar(
                select(User).where(User.telegram_id == recipient_telegram_id)
            )
        elif recipient_user_id is not None:
            # Backward-compatible path for already deployed clients that still
            # submit ROXY's internal UUID. New customer UI uses Telegram user ID.
            recipient = await session.get(User, recipient_user_id)
        else:
            raise PartnerRoxTransferError("Укажите ID пользователя")

        if recipient is None or not recipient.is_active:
            # Keep the response intentionally generic so transfer lookup cannot be
            # used to distinguish a missing account from a restricted account.
            raise PartnerRoxRecipientNotAllowed("Пользователь не найден или недоступен")
        return recipient

    @classmethod
    async def transfer(
        cls,
        session: AsyncSession,
        *,
        sender_user_id: uuid.UUID,
        recipient_user_id: uuid.UUID | None = None,
        recipient_telegram_id: int | None = None,
        amount_rox: int,
        idempotency_key: str,
    ) -> PartnerRoxTransferResult:
        if amount_rox <= 0:
            raise PartnerRoxTransferError("Сумма перевода должна быть больше нуля")
        key = idempotency_key.strip()
        if len(key) < 8 or len(key) > 96:
            raise PartnerRoxTransferError("Некорректный ключ операции")

        recipient = await cls._recipient(
            session,
            recipient_user_id=recipient_user_id,
            recipient_telegram_id=recipient_telegram_id,
        )
        if sender_user_id == recipient.id:
            raise PartnerRoxTransferError("Нельзя перевести ROX самому себе")

        transfer_id = cls._transfer_id(
            sender_user_id=sender_user_id,
            recipient_user_id=recipient.id,
            idempotency_key=key,
        )
        amount = Decimal(amount_rox)
        reference_id = str(transfer_id)

        # Serialize transfer intents from one sender before WalletService performs
        # its idempotency lookup. Without this lock, two concurrent retries can
        # both observe a missing transaction and the loser reaches the database
        # unique constraint instead of returning the already-created transfer.
        await WalletService.ensure_wallet(session, sender_user_id)
        sender_wallet = await session.scalar(
            select(Wallet).where(Wallet.user_id == sender_user_id).with_for_update()
        )
        if sender_wallet is None:  # pragma: no cover - ensure_wallet guarantees it.
            raise PartnerRoxTransferError("Кошелёк отправителя недоступен")

        sender_tx = await WalletService.debit(
            session,
            user_id=sender_user_id,
            amount=amount,
            kind="partner_rox_transfer_out",
            reference_type="partner_rox_transfer",
            reference_id=reference_id,
            idempotency_key=f"partner-rox:{key}:out",
        )
        recipient_tx = await WalletService.credit(
            session,
            user_id=recipient.id,
            amount=amount,
            kind="partner_rox_transfer_in",
            reference_type="partner_rox_transfer",
            reference_id=reference_id,
            idempotency_key=f"partner-rox:{key}:in",
        )
        return PartnerRoxTransferResult(
            transfer_id=transfer_id,
            recipient_user_id=recipient.id,
            recipient_telegram_id=recipient.telegram_id,
            sender_transaction=sender_tx,
            recipient_transaction=recipient_tx,
        )
