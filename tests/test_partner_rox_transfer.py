import random
from decimal import Decimal

import pytest

from app.db.models import ReferralRelation, User, Wallet
from app.db.session import SessionFactory
from app.services.partner_rox_transfer import PartnerRoxRecipientNotAllowed, PartnerRoxTransferService
from app.services.wallet import InsufficientBalanceError, WalletService


def _telegram_id() -> int:
    return random.randint(400_000_000_000, 899_999_999_999)


@pytest.mark.asyncio
async def test_direct_referral_rox_transfer_is_idempotent() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Creator")
        session.add_all([sender, recipient])
        await session.flush()
        session.add(ReferralRelation(inviter_user_id=sender.id, referred_user_id=recipient.id))
        await WalletService.ensure_wallet(session, sender.id)
        await WalletService.ensure_wallet(session, recipient.id)
        await WalletService.credit(session, user_id=sender.id, amount=Decimal("7000"), kind="test_credit", idempotency_key=f"seed:{sender.id}")

        first = await PartnerRoxTransferService.transfer(session, sender_user_id=sender.id, recipient_user_id=recipient.id, amount_rox=5500, idempotency_key="gift-5500-creator")
        replay = await PartnerRoxTransferService.transfer(session, sender_user_id=sender.id, recipient_user_id=recipient.id, amount_rox=5500, idempotency_key="gift-5500-creator")
        await session.commit()

        assert replay.transfer_id == first.transfer_id
        assert replay.sender_transaction.id == first.sender_transaction.id
        assert replay.recipient_transaction.id == first.recipient_transaction.id
        assert (await session.get(Wallet, sender.id)).balance == Decimal("1500.00")
        assert (await session.get(Wallet, recipient.id)).balance == Decimal("5500.00")


@pytest.mark.asyncio
async def test_rox_transfer_rejects_non_direct_referral() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Other")
        session.add_all([sender, recipient])
        await session.flush()
        await WalletService.ensure_wallet(session, sender.id)
        await WalletService.ensure_wallet(session, recipient.id)
        await WalletService.credit(session, user_id=sender.id, amount=Decimal("6000"), kind="test_credit", idempotency_key=f"seed:{sender.id}")

        with pytest.raises(PartnerRoxRecipientNotAllowed):
            await PartnerRoxTransferService.transfer(session, sender_user_id=sender.id, recipient_user_id=recipient.id, amount_rox=5500, idempotency_key="not-direct")


@pytest.mark.asyncio
async def test_rox_transfer_rejects_overdraft() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Creator")
        session.add_all([sender, recipient])
        await session.flush()
        session.add(ReferralRelation(inviter_user_id=sender.id, referred_user_id=recipient.id))
        await WalletService.ensure_wallet(session, sender.id)
        await WalletService.ensure_wallet(session, recipient.id)
        await WalletService.credit(session, user_id=sender.id, amount=Decimal("100"), kind="test_credit", idempotency_key=f"seed:{sender.id}")

        with pytest.raises(InsufficientBalanceError):
            await PartnerRoxTransferService.transfer(session, sender_user_id=sender.id, recipient_user_id=recipient.id, amount_rox=5500, idempotency_key="too-large-gift")
