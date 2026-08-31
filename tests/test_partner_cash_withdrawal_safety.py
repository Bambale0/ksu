from __future__ import annotations

import asyncio
import random
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import ReferralReward, User
from app.db.partner_wallet_models import PartnerWithdrawalRequest
from app.db.session import SessionFactory
from app.services.partner import PartnerInsufficientFunds, PartnerWithdrawalIdempotencyConflict
from app.services.partner_wallet import (
    PartnerWalletTransferInsufficientFunds,
    PartnerWalletTransferService,
)
from app.services.wallet import WalletService


ROOT = Path(__file__).resolve().parents[1]


def _telegram_id() -> int:
    return 99_800_000_000_000 + random.randint(1, 999_999_999)


async def _user(session, name: str) -> User:
    item = User(telegram_id=_telegram_id(), first_name=name)
    session.add(item)
    await session.flush()
    return item


async def _seed_available_reward(
    session,
    *,
    partner: User,
    buyer: User,
    amount: Decimal = Decimal("30"),
) -> None:
    source_tx = await WalletService.credit(
        session,
        user_id=buyer.id,
        amount=Decimal("1"),
        kind="partner_safety_test",
        reference_type="partner_safety_test",
        reference_id=str(uuid.uuid4()),
        idempotency_key=f"partner-safety-source:{uuid.uuid4()}",
    )
    session.add(
        ReferralReward(
            partner_user_id=partner.id,
            source_user_id=buyer.id,
            source_transaction_id=source_tx.id,
            level=1,
            percent=Decimal("30"),
            amount=amount,
            status="available",
        )
    )
    await session.flush()


def test_rox_never_enters_cash_withdrawal_contract() -> None:
    api = (ROOT / "app/api/v1/referrals.py").read_text(encoding="utf-8")
    referrals = (ROOT / "app/services/referrals.py").read_text(encoding="utf-8")
    page = (ROOT / "frontend/mini-app/app/partner-wallet/page.tsx").read_text(encoding="utf-8")
    admin = (ROOT / "app/services/admin_partners.py").read_text(encoding="utf-8")

    assert '"withdrawable_rub"' in api
    assert '"withdrawable_rox"' not in api
    assert '"amount_rub"' in api
    assert "_paid_rub_basis" in referrals
    assert 'currency == "RUB"' in referrals
    assert 'payload.get("referral_basis_rub")' in referrals
    assert "ROX — внутренняя валюта ROXY и на карту не выводится" in page
    assert "ROX, бонусы и пополнения в вывод не входят" in page
    assert "PartnerWalletTransferService.accounting" in admin
    assert 'accounting["reserved_or_paid"]' in admin
    assert 'accounting["transferred_to_rox"]' in admin


@pytest.mark.asyncio
async def test_cash_withdrawal_request_replay_is_durable_and_payload_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("1"))
    async with SessionFactory() as session:
        partner = await _user(session, "Cash partner")
        buyer = await _user(session, "Cash buyer")
        await _seed_available_reward(session, partner=partner, buyer=buyer)
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
async def test_cash_withdrawal_and_rox_conversion_cannot_double_spend_partner_income(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("1"))
    async with SessionFactory() as session:
        partner = await _user(session, "Race partner")
        buyer = await _user(session, "Race buyer")
        await _seed_available_reward(session, partner=partner, buyer=buyer)
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
            except (PartnerWalletTransferInsufficientFunds, PartnerInsufficientFunds):
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
            except (PartnerWalletTransferInsufficientFunds, PartnerInsufficientFunds):
                await session.rollback()
                return "blocked"

    outcomes = await asyncio.gather(convert(), withdraw())
    assert outcomes.count("blocked") == 1
    assert sum(item in {"converted", "withdrawn"} for item in outcomes) == 1

    async with SessionFactory() as session:
        accounting = await PartnerWalletTransferService.accounting(session, partner_id)
        assert accounting["available"] == Decimal("10.00")
