import random
from decimal import Decimal

import pytest

from app.db.models import User, Wallet
from app.db.session import SessionFactory
from app.services.partner_rox_transfer import (
    PartnerRoxRecipientNotAllowed,
    PartnerRoxTransferError,
    PartnerRoxTransferService,
)
from app.services.wallet import (
    IdempotencyConflictError,
    InsufficientBalanceError,
    WalletService,
)


def _telegram_id() -> int:
    return random.randint(400_000_000_000, 899_999_999_999)


@pytest.mark.asyncio
async def test_rox_transfer_to_any_active_user_by_telegram_id_is_idempotent() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Creator")
        session.add_all([sender, recipient])
        await session.flush()
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
            recipient_telegram_id=recipient.telegram_id,
            amount_rox=5500,
            idempotency_key="gift-5500-creator",
        )
        replay = await PartnerRoxTransferService.transfer(
            session,
            sender_user_id=sender.id,
            recipient_telegram_id=recipient.telegram_id,
            amount_rox=5500,
            idempotency_key="gift-5500-creator",
        )
        await session.commit()

        assert first.recipient_user_id == recipient.id
        assert first.recipient_telegram_id == recipient.telegram_id
        assert replay.transfer_id == first.transfer_id
        assert replay.sender_transaction.id == first.sender_transaction.id
        assert replay.recipient_transaction.id == first.recipient_transaction.id
        assert (await session.get(Wallet, sender.id)).balance == Decimal("1500.00")
        assert (await session.get(Wallet, recipient.id)).balance == Decimal("5500.00")


@pytest.mark.asyncio
async def test_rox_transfer_keeps_internal_uuid_compatibility() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Legacy recipient")
        session.add_all([sender, recipient])
        await session.flush()
        await WalletService.credit(
            session,
            user_id=sender.id,
            amount=Decimal("100"),
            kind="test_credit",
            idempotency_key=f"seed:{sender.id}",
        )

        result = await PartnerRoxTransferService.transfer(
            session,
            sender_user_id=sender.id,
            recipient_user_id=recipient.id,
            amount_rox=25,
            idempotency_key="legacy-uuid-transfer",
        )
        await session.commit()

        assert result.recipient_user_id == recipient.id
        assert result.recipient_telegram_id == recipient.telegram_id
        assert (await session.get(Wallet, recipient.id)).balance == Decimal("25.00")


@pytest.mark.asyncio
async def test_rox_transfer_rejects_missing_or_inactive_user() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        inactive = User(telegram_id=_telegram_id(), first_name="Restricted", is_active=False)
        session.add_all([sender, inactive])
        await session.flush()

        with pytest.raises(PartnerRoxRecipientNotAllowed):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_telegram_id=_telegram_id(),
                amount_rox=50,
                idempotency_key="missing-user",
            )
        with pytest.raises(PartnerRoxRecipientNotAllowed):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_telegram_id=inactive.telegram_id,
                amount_rox=50,
                idempotency_key="inactive-user",
            )


@pytest.mark.asyncio
async def test_rox_transfer_rejects_self_transfer() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        session.add(sender)
        await session.flush()

        with pytest.raises(PartnerRoxTransferError, match="самому себе"):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_telegram_id=sender.telegram_id,
                amount_rox=50,
                idempotency_key="self-transfer",
            )


@pytest.mark.asyncio
async def test_rox_transfer_rejects_overdraft() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Creator")
        session.add_all([sender, recipient])
        await session.flush()
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
                recipient_telegram_id=recipient.telegram_id,
                amount_rox=5500,
                idempotency_key="too-large-gift",
            )


@pytest.mark.asyncio
async def test_rox_transfer_rejects_idempotency_key_for_different_intent() -> None:
    async with SessionFactory() as session:
        sender = User(telegram_id=_telegram_id(), first_name="Sponsor")
        recipient = User(telegram_id=_telegram_id(), first_name="Creator")
        other = User(telegram_id=_telegram_id(), first_name="Other")
        session.add_all([sender, recipient, other])
        await session.flush()
        for user in (sender, recipient, other):
            await WalletService.ensure_wallet(session, user.id)
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
            recipient_telegram_id=recipient.telegram_id,
            amount_rox=5500,
            idempotency_key=key,
        )

        with pytest.raises(IdempotencyConflictError):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_telegram_id=recipient.telegram_id,
                amount_rox=5000,
                idempotency_key=key,
            )
        with pytest.raises(IdempotencyConflictError):
            await PartnerRoxTransferService.transfer(
                session,
                sender_user_id=sender.id,
                recipient_telegram_id=other.telegram_id,
                amount_rox=5500,
                idempotency_key=key,
            )
