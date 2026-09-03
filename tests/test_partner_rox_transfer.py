import random
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import ReferralRelation, User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.services.partner_rox_transfer import (
    PartnerRoxRecipientNotAllowed,
    PartnerRoxTransferService,
)
from app.services.wallet import IdempotencyConflictError, InsufficientBalanceError, WalletService


def _telegram_id() -> int:
    return random.randint(400_000_000_000, 899_999_999_999)


@pytest.mark.asyncio
async def test_direct_referral_can_receive_5500_rox_idempotently() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Creator")
        session.add_all([sender, recipient])
        await session.flush()
        session.add(
            ReferralRelation(
                inviter_user_id=sender.id,
                referred_user_id=recipient.id,
            )
        )
        await WalletService.ensure_wallet(session, sender.id)
        await WalletService.ensure_wallet(session, recipient.id)
        await WalletService.credit(
            session,
            user_id=sender.id,
            amount=Decimal("7000"),
            kind="test_credit",
            idempotency_key=f"seed:{sender.id}",
        )

        first = await PartnerRoxTransferService.transfer(
            session,
            sender_user_id=sender.id,
            recipient_user_id=recipient.id,
            amount_rox=5500,
            idempotency_key="gift-5500-creator",
        )
        replay = await PartnerRoxTransferService.transfer(
            session,
            sender_user_id=sender.id,
            recipient_user_id=recipient.id,
            amount_rox=5500,
            idempotency_key="gift-5500-creator",
        )
        await session.commit()

        assert replay.transfer_id == first.transfer_id
        assert replay.sender_transaction.id == first.sender_transaction.id
        assert replay.recipient_transaction.id == first.recipient_transaction.id
        assert (await session.get(Wallet, sender.id)).balance == Decimal("1500.00")
        assert (await session.get(Wallet, recipient.id)).balance == Decimal("5500.00")

        transfer_txs = list(
            (
                await session.scalars(
                    select(WalletTransaction).where(
                        WalletTransaction.reference_type == "partner_rox_transfer",
                        WalletTransaction.reference_id == str(first.transfer_id),
                    )
                )
            ).all()
        )
        assert len(transfer_txs) == 2
        assert sorted(Decimal(tx.amount) for tx in transfer_txs) == [
            Decimal("-5500.00"),
            Decimal("5500.00"),
        ]


@pytest.mark.asyncio
async def test_rox_transfer_rejects_non_direct_referral_without_balance_changes() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        direct = User(telegram_id=_telegram_id(), first_name="Direct")
        second_line = User(telegram_id=_telegram_id(), first_name="Second")
        session.add_all([sender, direct, second_line])
        await session.flush()
        session.add_all(
            [
                ReferralRelation(inviter_user_id=sender.id, referred_user_id=direct.id),
                ReferralRelation(inviter_user_id=direct.id, referred_user_id=second_line.id),
            ]
        )
        await WalletService.ensure_wallet(session, sender.id)
        await WalletService.ensure_wallet(session, second_line.id)
        await WalletService.credit(
            session,
            user_id=sender.id,
            amount=Decimal("6000"),
            kind="test_credit",
            idempotency_key=f"seed:{sender.id}",
        )

        with pytest.raises(PartnerRoxRecipientNotAllowed):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_user_id=second_line.id,
                amount_rox=5500,
                idempotency_key="second-line-gift",
            )

        assert (await session.get(Wallet, sender.id)).balance == Decimal("6000.00")
        assert (await session.get(Wallet, second_line.id)).balance == Decimal("0.00")
        await session.rollback()


@pytest.mark.asyncio
async def test_rox_transfer_overdraft_rolls_back_recipient_credit() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Creator")
        session.add_all([sender, recipient])
        await session.flush()
        session.add(
            ReferralRelation(inviter_user_id=sender.id, referred_user_id=recipient.id)
        )
        await WalletService.ensure_wallet(session, sender.id)
        await WalletService.ensure_wallet(session, recipient.id)
        await WalletService.credit(
            session,
            user_id=sender.id,
            amount=Decimal("100"),
            kind="test_credit",
            idempotency_key=f"seed:{sender.id}",
        )

        with pytest.raises(InsufficientBalanceError):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_user_id=recipient.id,
                amount_rox=5500,
                idempotency_key="too-large-gift",
            )

        assert (await session.get(Wallet, sender.id)).balance == Decimal("100.00")
        assert (await session.get(Wallet, recipient.id)).balance == Decimal("0.00")
        await session.rollback()


@pytest.mark.asyncio
async def test_rox_transfer_rejects_idempotency_key_reuse_for_different_intent() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Creator")
        other = User(telegram_id=_telegram_id(), first_name="Other")
        session.add_all([sender, recipient, other])
        await session.flush()
        session.add_all(
            [
                ReferralRelation(inviter_user_id=sender.id, referred_user_id=recipient.id),
                ReferralRelation(inviter_user_id=sender.id, referred_user_id=other.id),
            ]
        )
        await WalletService.ensure_wallet(session, sender.id)
        await WalletService.ensure_wallet(session, recipient.id)
        await WalletService.ensure_wallet(session, other.id)
        await WalletService.credit(
            session,
            user_id=sender.id,
            amount=Decimal("12000"),
            kind="test_credit",
            idempotency_key=f"seed:{sender.id}",
        )
        key = "same-transfer-intent"
        await PartnerRoxTransferService.transfer(
            session,
            sender_user_id=sender.id,
            recipient_user_id=recipient.id,
            amount_rox=5500,
            idempotency_key=key,
        )

        with pytest.raises(IdempotencyConflictError):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_user_id=recipient.id,
                amount_rox=5000,
                idempotency_key=key,
            )
        with pytest.raises(IdempotencyConflictError):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_user_id=other.id,
                amount_rox=5500,
                idempotency_key=key,
            )
        await session.rollback()
