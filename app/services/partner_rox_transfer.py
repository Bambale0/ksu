from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReferralRelation, User
from app.services.wallet import WalletService, WalletTransaction


class PartnerRoxTransferError(ValueError):
    pass


class PartnerRoxRecipientNotAllowed(PartnerRoxTransferError):
    pass


@dataclass(frozen=True)
class PartnerRoxTransferResult:
    transfer_id: uuid.UUID
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

    @classmethod
    async def transfer(
        cls,
        session: AsyncSession,
        *,
        sender_user_id: uuid.UUID,
        recipient_user_id: uuid.UUID,
        amount_rox: int,
        idempotency_key: str,
    ) -> PartnerRoxTransferResult:
        if sender_user_id == recipient_user_id:
            raise PartnerRoxTransferError("Cannot transfer ROX to yourself")
        if amount_rox <= 0:
            raise PartnerRoxTransferError("Transfer amount must be positive")
        key = idempotency_key.strip()
        if len(key) < 8 or len(key) > 96:
            raise PartnerRoxTransferError("Valid idempotency key is required")

        relation = await session.scalar(
            select(ReferralRelation).where(
                ReferralRelation.inviter_user_id == sender_user_id,
                ReferralRelation.referred_user_id == recipient_user_id,
            )
        )
        if relation is None:
            raise PartnerRoxRecipientNotAllowed(
                "ROX can only be transferred to your direct referral"
            )
        recipient = await session.get(User, recipient_user_id)
        if recipient is None or not recipient.is_active:
            raise PartnerRoxRecipientNotAllowed("Recipient is unavailable")

        transfer_id = cls._transfer_id(
            sender_user_id=sender_user_id,
            recipient_user_id=recipient_user_id,
            idempotency_key=key,
        )
        amount = Decimal(amount_rox)
        reference_id = str(transfer_id)

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
            user_id=recipient_user_id,
            amount=amount,
            kind="partner_rox_transfer_in",
            reference_type="partner_rox_transfer",
            reference_id=reference_id,
            idempotency_key=f"partner-rox:{key}:in",
        )
        return PartnerRoxTransferResult(
            transfer_id=transfer_id,
            sender_transaction=sender_tx,
            recipient_transaction=recipient_tx,
        )
