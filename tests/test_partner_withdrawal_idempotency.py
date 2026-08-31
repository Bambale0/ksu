from __future__ import annotations

import asyncio
import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import ReferralRelation, User
from app.db.partner_wallet_models import PartnerWalletTransfer, PartnerWithdrawalRequest
from app.db.session import SessionFactory
from app.services.partner import PartnerWithdrawalIdempotencyConflict
from app.services.partner_wallet import (
    PartnerWalletTransferInsufficientFunds,
    PartnerWalletTransferService,
)
from app.services.referrals import ReferralService
from app.services.wallet import WalletService

ROOT = Path(__file__).resolve().parents[1]


def _telegram_id() -> int:
    return 99_800_000_000_000 + random.randint(1, 999_999_999)


async def _user(session, name: str) -> User:
    item = User(telegram_id=_telegram_id(), first_name=name)
    session.add(item)
    await session.flush()
    return item


async def _seed_reward(session, *, partner: User, buyer: User) -> None:
    session.add(ReferralRelation(referred_user_id=buyer.id, inviter_user_id=partner.id))
    source_tx = await WalletService.credit(
        session,
        user_id=buyer.id,
        amount=Decimal("100"),
        kind="payment",
        reference_type="withdrawal_idempotency_test",
        reference_id=str(uuid.uuid4()),
        idempotency_key=f"withdrawal-source:{uuid.uuid4()}",
    )
    await ReferralService.accrue_from_payment(
        session,
        source_user_id=buyer.id,
        source_transaction_id=source_tx.id,
        payment_amount=Decimal("100"),
    )


def test_withdrawal_endpoint_requires_transport_idempotency_key() -> None:
    source = (ROOT / "app/api/v1/referrals.py").read_text(encoding="utf-8")
    assert 'alias="Idempotency-Key"' in source
    assert "PartnerWalletTransferService.create_cash_withdrawal" in source
    assert "PartnerWithdrawalIdempotencyConflict" in source


def test_withdrawal_idempotency_has_durable_schema() -> None:
    model = (ROOT / "app/db/partner_wallet_models.py").read_text(encoding="utf-8")
    migration = (ROOT / "alembic/versions/0033_partner_withdrawal_idempotency.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "partner_withdrawal_requests",
        "uq_partner_withdrawal_requests_user_idempotency",
        "withdrawal_id",
        "idempotency_key",
    ):
        assert token in model
        assert token in migration


@pytest.mark.asyncio
async def test_cash_withdrawal_replay_is_durable_and_payload_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("1"))

    async with SessionFactory() as session:
        partner = await _user(session, "Cash partner")
        buyer = await _user(session, "Cash buyer")
        await _seed_reward(session, partner=partner, buyer=buyer)
        await session.commit()

        key = f"cash-withdrawal-{uuid.uuid4()}"
        first = await PartnerWalletTransferService.create_cash_withdrawal(
            session,
            user_id=partner.id,
            amount=Decimal("20"),
            requisites="SBP +79990000000",
            idempotency_key=key,
        )
        await session.commit()

        replay = await PartnerWalletTransferService.create_cash_withdrawal(
            session,
            user_id=partner.id,
            amount=Decimal("20.00"),
            requisites=" SBP +79990000000 ",
            idempotency_key=key,
        )
        assert replay.id == first.id
        assert int(
            (
                await session.scalar(
                    select(func.count()).select_from(PartnerWithdrawalRequest).where(
                        PartnerWithdrawalRequest.user_id == partner.id
                    )
                )
            )
            or 0
        ) == 1

        with pytest.raises(PartnerWithdrawalIdempotencyConflict):
            await PartnerWalletTransferService.create_cash_withdrawal(
                session,
                user_id=partner.id,
                amount=Decimal("21"),
                requisites="SBP +79990000000",
                idempotency_key=key,
            )


@pytest.mark.asyncio
async def test_cash_withdrawal_and_rox_conversion_cannot_double_spend_same_income(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("1"))

    async with SessionFactory() as session:
        partner = await _user(session, "Race partner")
        buyer = await _user(session, "Race buyer")
        await _seed_reward(session, partner=partner, buyer=buyer)
        await session.commit()
        partner_id = partner.id

    async def convert() -> str:
        async with SessionFactory() as session:
            try:
                await PartnerWalletTransferService.transfer(
                    session,
                    user_id=partner_id,
                    amount=Decimal("20"),
                    idempotency_key=f"race-transfer-{uuid.uuid4()}",
                )
                await session.commit()
                return "converted"
            except PartnerWalletTransferInsufficientFunds:
                await session.rollback()
                return "blocked"

    async def withdraw() -> str:
        async with SessionFactory() as session:
            try:
                await PartnerWalletTransferService.create_cash_withdrawal(
                    session,
                    user_id=partner_id,
                    amount=Decimal("20"),
                    requisites="SBP +79990000000",
                    idempotency_key=f"race-withdrawal-{uuid.uuid4()}",
                )
                await session.commit()
                return "withdrawn"
            except PartnerWalletTransferInsufficientFunds:
                await session.rollback()
                return "blocked"

    outcomes = await asyncio.gather(convert(), withdraw())
    assert outcomes.count("blocked") == 1
    assert sum(item in {"converted", "withdrawn"} for item in outcomes) == 1

    async with SessionFactory() as session:
        accounting = await PartnerWalletTransferService.accounting(session, partner_id)
        assert accounting["available"] == Decimal("10.00")
        transfers = int(
            (
                await session.scalar(
                    select(func.count()).select_from(PartnerWalletTransfer).where(
                        PartnerWalletTransfer.user_id == partner_id
                    )
                )
            )
            or 0
        )
        requests = int(
            (
                await session.scalar(
                    select(func.count()).select_from(PartnerWithdrawalRequest).where(
                        PartnerWithdrawalRequest.user_id == partner_id
                    )
                )
            )
            or 0
        )
        assert transfers + requests == 1
