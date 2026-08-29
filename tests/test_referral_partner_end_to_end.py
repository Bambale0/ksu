from __future__ import annotations

import asyncio
import random
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import (
    AdminAccount,
    PartnerWithdrawal,
    Payment,
    ReferralRelation,
    ReferralReward,
    User,
    Wallet,
)
from app.db.partner_wallet_models import PartnerWalletTransfer, PartnerWithdrawalRequest
from app.db.payment_models import PaymentReversal
from app.db.session import SessionFactory
from app.providers.card_checkout import CardCheckoutClient
from app.providers.payments import CreatedPayment
from app.services.admin_partners import AdminPartnerService
from app.services.card_payments import CardPaymentService
from app.services.partner import PartnerWithdrawalIdempotencyConflict
from app.services.partner_wallet import (
    PartnerWalletTransferIdempotencyConflict,
    PartnerWalletTransferInsufficientFunds,
    PartnerWalletTransferService,
)
from app.services.payments import PaymentService
from app.services.referrals import ReferralService
from app.services.wallet import WalletService


def _telegram_id() -> int:
    return 99_700_000_000_000 + random.randint(1, 999_999_999)


async def _user(session, name: str) -> User:
    item = User(telegram_id=_telegram_id(), first_name=name)
    session.add(item)
    await session.flush()
    return item


async def _seed_referral_reward(
    session,
    *,
    partner: User,
    buyer: User,
    basis: Decimal = Decimal("100"),
) -> ReferralReward:
    session.add(ReferralRelation(referred_user_id=buyer.id, inviter_user_id=partner.id))
    source_tx = await WalletService.credit(
        session,
        user_id=buyer.id,
        amount=basis,
        kind="payment",
        reference_type="test_payment",
        reference_id=str(uuid.uuid4()),
        idempotency_key=f"partner-e2e-source:{uuid.uuid4()}",
    )
    await ReferralService.accrue_from_payment(
        session,
        source_user_id=buyer.id,
        source_transaction_id=source_tx.id,
        payment_amount=basis,
    )
    reward = await session.scalar(
        select(ReferralReward).where(
            ReferralReward.partner_user_id == partner.id,
            ReferralReward.source_transaction_id == source_tx.id,
            ReferralReward.level == 1,
        )
    )
    assert reward is not None
    return reward


@pytest.mark.asyncio
async def test_card_gift_rox_never_increase_referral_commission_and_refunds_are_proportional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "card_packages_json",
        '{"p300":{"credits":"300","prices":{"RUB":"326.10"}}}',
    )
    monkeypatch.setattr(settings, "card_offer_id", "offer-referral-e2e")
    monkeypatch.setattr(settings, "card_api_key", "e2e-card-key")
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    monkeypatch.setattr(settings, "referral_second_percent", Decimal("5"))

    async def fake_get_products(self: CardCheckoutClient) -> dict[str, object]:
        return {
            "items": [
                {
                    "id": "product-referral-e2e",
                    "offers": [{"id": "offer-referral-e2e", "isDynamicPrice": True}],
                }
            ]
        }

    async def fake_create_invoice(
        self: CardCheckoutClient,
        *,
        email: str,
        offer_id: str,
        currency: str,
        amount: Decimal | None,
        payment_provider: str | None = None,
    ) -> CreatedPayment:
        return CreatedPayment(
            external_id=f"card-referral-e2e-{uuid.uuid4()}",
            payment_url="https://pay.example/referral-e2e",
            raw={"status": "pending"},
        )

    monkeypatch.setattr(CardCheckoutClient, "get_products", fake_get_products)
    monkeypatch.setattr(CardCheckoutClient, "create_invoice", fake_create_invoice)

    async with SessionFactory() as session:
        second_line = await _user(session, "Second line")
        first_line = await _user(session, "First line")
        buyer = await _user(session, "Buyer")
        session.add_all(
            [
                ReferralRelation(referred_user_id=first_line.id, inviter_user_id=second_line.id),
                ReferralRelation(referred_user_id=buyer.id, inviter_user_id=first_line.id),
            ]
        )
        await session.commit()

        payment = await CardPaymentService.create(
            session,
            user_id=buyer.id,
            package_id="p300",
            currency="RUB",
            billing_email="buyer@example.com",
            request_key=str(uuid.uuid4()),
        )
        await CardPaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "paid"},
        )

        wallet = await session.get(Wallet, buyer.id)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("350.00")
        rewards = list(
            (
                await session.scalars(
                    select(ReferralReward)
                    .where(ReferralReward.source_user_id == buyer.id)
                    .order_by(ReferralReward.level)
                )
            ).all()
        )
        assert [(item.level, Decimal(item.amount)) for item in rewards] == [
            (1, Decimal("90.00")),
            (2, Decimal("15.00")),
        ]

        await CardPaymentService.complete(
            session,
            payment_id=payment.id,
            provider_payload={"status": "paid", "retry": True},
        )
        assert int(
            (
                await session.scalar(
                    select(func.count()).select_from(ReferralReward).where(
                        ReferralReward.source_user_id == buyer.id
                    )
                )
            )
            or 0
        ) == 2

        await PaymentService.apply_reversal(
            session,
            payment_id=payment.id,
            amount=Decimal("163.05"),
            provider="card",
            idempotency_key=f"refund-half:{payment.id}",
            reason="e2e partial refund",
            provider_payload={"refunded": "163.05"},
        )
        assert (await PartnerWalletTransferService.accounting(session, first_line.id))["total_earned"] == Decimal("45.00")
        assert (await PartnerWalletTransferService.accounting(session, second_line.id))["total_earned"] == Decimal("7.50")

        await PaymentService.apply_reversal(
            session,
            payment_id=payment.id,
            amount=Decimal("163.05"),
            provider="card",
            idempotency_key=f"refund-rest:{payment.id}",
            reason="e2e full refund",
            provider_payload={"refunded": "326.10"},
        )
        assert (await PartnerWalletTransferService.accounting(session, first_line.id))["total_earned"] == Decimal("0.00")
        assert (await PartnerWalletTransferService.accounting(session, second_line.id))["total_earned"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_partner_wallet_transfer_replay_must_match_original_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    async with SessionFactory() as session:
        partner = await _user(session, "Partner")
        buyer = await _user(session, "Buyer")
        await _seed_referral_reward(session, partner=partner, buyer=buyer)
        await session.commit()

        key = f"partner-transfer-{uuid.uuid4()}"
        first = await PartnerWalletTransferService.transfer(
            session, user_id=partner.id, amount=Decimal("10"), idempotency_key=key
        )
        await session.commit()
        replay = await PartnerWalletTransferService.transfer(
            session, user_id=partner.id, amount=Decimal("10.00"), idempotency_key=key
        )
        assert replay.id == first.id
        with pytest.raises(PartnerWalletTransferIdempotencyConflict):
            await PartnerWalletTransferService.transfer(
                session, user_id=partner.id, amount=Decimal("11"), idempotency_key=key
            )
        assert int(
            (
                await session.scalar(
                    select(func.count()).select_from(PartnerWalletTransfer).where(
                        PartnerWalletTransfer.user_id == partner.id
                    )
                )
            )
            or 0
        ) == 1


@pytest.mark.asyncio
async def test_cash_withdrawal_request_replay_is_durable_and_payload_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("1"))
    async with SessionFactory() as session:
        partner = await _user(session, "Cash partner")
        buyer = await _user(session, "Cash buyer")
        await _seed_referral_reward(session, partner=partner, buyer=buyer)
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
async def test_cash_withdrawal_and_rox_conversion_cannot_double_spend_same_partner_income(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("1"))
    async with SessionFactory() as session:
        partner = await _user(session, "Race partner")
        buyer = await _user(session, "Race buyer")
        await _seed_referral_reward(session, partner=partner, buyer=buyer)
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


@pytest.mark.asyncio
async def test_refund_invalidates_pending_payout_and_admin_analytics_are_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("1"))
    async with SessionFactory() as session:
        admin_user = await _user(session, "Admin")
        admin = AdminAccount(user_id=admin_user.id, role="admin", is_active=True)
        partner = await _user(session, "Refunded partner")
        buyer = await _user(session, "Refunded buyer")
        session.add(admin)
        reward = await _seed_referral_reward(session, partner=partner, buyer=buyer)
        payment = Payment(
            user_id=buyer.id,
            provider="audit",
            external_id=f"audit-payment-{uuid.uuid4()}",
            amount=Decimal("100"),
            currency="RUB",
            rox_amount=Decimal("100"),
            status="refunded",
            payload={},
        )
        session.add(payment)
        await session.flush()
        reversal = PaymentReversal(
            payment_id=payment.id,
            provider="audit",
            idempotency_key=f"audit-reversal-{uuid.uuid4()}",
            amount=Decimal("100"),
            credits=Decimal("100"),
            reason="refund",
            provider_payload={},
        )
        session.add(reversal)
        await session.flush()
        withdrawal = await PartnerWalletTransferService.create_cash_withdrawal(
            session,
            user_id=partner.id,
            amount=Decimal("30"),
            requisites="SBP +79990000000",
            idempotency_key=f"refund-withdrawal-{uuid.uuid4()}",
        )
        await ReferralService.reverse_payment_rewards(
            session,
            source_transaction_id=reward.source_transaction_id,
            payment_reversal_id=reversal.id,
            cumulative_ratio=Decimal("1"),
        )
        await session.commit()

        with pytest.raises(ValueError, match="no longer backed"):
            await AdminPartnerService.update_withdrawal(
                session,
                admin=admin,
                withdrawal_id=withdrawal.id,
                status="processing",
                reason="attempt after refund",
                idempotency_key=f"admin-payout-{uuid.uuid4()}",
                request_id=str(uuid.uuid4()),
                confirmed=True,
                step_up_valid=True,
            )
        await session.rollback()
        stored = await session.get(PartnerWithdrawal, withdrawal.id)
        assert stored is not None and stored.status == "pending"
        analytics = await AdminPartnerService.analytics(session, admin=admin)
        reversed_row = next(item for item in analytics["rewards"] if item["status"] == "reversed")
        assert Decimal(reversed_row["gross_amount"]) == Decimal("30.00")
        assert Decimal(reversed_row["reversed_amount"]) == Decimal("30.00")
        assert Decimal(reversed_row["amount"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_admin_can_open_withdrawal_older_than_first_page() -> None:
    async with SessionFactory() as session:
        admin_user = await _user(session, "Detail admin")
        admin = AdminAccount(user_id=admin_user.id, role="admin", is_active=True)
        partner = await _user(session, "Detail partner")
        session.add(admin)
        rows = [
            PartnerWithdrawal(
                user_id=partner.id,
                amount=Decimal("1"),
                status="canceled",
                requisites={"details": f"row-{index}"},
            )
            for index in range(101)
        ]
        session.add_all(rows)
        await session.commit()
        detail = await AdminPartnerService.withdrawal_detail(
            session,
            admin=admin,
            withdrawal_id=rows[0].id,
        )
        assert detail["id"] == str(rows[0].id)
        assert detail["requisites"] != "[restricted]"
