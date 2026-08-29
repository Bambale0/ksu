from __future__ import annotations

import random
import uuid
from decimal import Decimal

import pytest

from app.core.config import settings
from app.db.models import AdminAccount, Payment, ReferralRelation, User
from app.db.payment_models import PaymentReversal
from app.db.session import SessionFactory
from app.services.admin_partners import AdminPartnerService
from app.services.partner_wallet import PartnerWalletTransferService
from app.services.referrals import ReferralService
from app.services.wallet import WalletService


def _telegram_id() -> int:
    return random.randint(9_810_000_000_000_000, 9_899_999_999_999_999)


@pytest.mark.asyncio
async def test_admin_payout_recheck_counts_already_converted_partner_rox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "referral_first_percent", Decimal("30"))
    monkeypatch.setattr(settings, "partner_min_withdrawal_rub", Decimal("1"))

    async with SessionFactory() as session:
        admin_user = User(telegram_id=_telegram_id(), first_name="Admin")
        partner = User(telegram_id=_telegram_id(), first_name="Partner")
        buyer = User(telegram_id=_telegram_id(), first_name="Buyer")
        session.add_all([admin_user, partner, buyer])
        await session.flush()
        admin = AdminAccount(user_id=admin_user.id, role="admin", is_active=True)
        session.add(admin)
        session.add(ReferralRelation(referred_user_id=buyer.id, inviter_user_id=partner.id))

        source_tx = await WalletService.credit(
            session,
            user_id=buyer.id,
            amount=Decimal("100"),
            kind="payment",
            reference_type="test_payment",
            reference_id=str(uuid.uuid4()),
            idempotency_key=f"payout-backing-source:{uuid.uuid4()}",
        )
        await ReferralService.accrue_from_payment(
            session,
            source_user_id=buyer.id,
            source_transaction_id=source_tx.id,
            payment_amount=Decimal("100"),
        )
        await session.commit()

        await PartnerWalletTransferService.transfer(
            session,
            user_id=partner.id,
            amount=Decimal("10"),
            idempotency_key=f"payout-backing-transfer:{uuid.uuid4()}",
        )
        withdrawal = await PartnerWalletTransferService.create_cash_withdrawal(
            session,
            user_id=partner.id,
            amount=Decimal("20"),
            requisites="SBP +79990000000",
            idempotency_key=f"payout-backing-withdrawal:{uuid.uuid4()}",
        )

        payment = Payment(
            user_id=buyer.id,
            provider="audit",
            external_id=f"audit-{uuid.uuid4()}",
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
            amount=Decimal("20"),
            credits=Decimal("20"),
            reason="partial refund",
            provider_payload={},
        )
        session.add(reversal)
        await session.flush()
        await ReferralService.reverse_payment_rewards(
            session,
            source_transaction_id=source_tx.id,
            payment_reversal_id=reversal.id,
            cumulative_ratio=Decimal("0.20"),
        )
        await session.commit()

        accounting = await PartnerWalletTransferService.accounting(session, partner.id)
        assert accounting["total_earned"] == Decimal("24.00")
        assert accounting["transferred_to_rox"] == Decimal("10.00")
        assert accounting["reserved_or_paid"] == Decimal("20.00")

        with pytest.raises(ValueError, match="no longer backed"):
            await AdminPartnerService.update_withdrawal(
                session,
                admin=admin,
                withdrawal_id=withdrawal.id,
                status="processing",
                reason="must not exceed post-refund earnings",
                idempotency_key=f"admin-payout:{uuid.uuid4()}",
                request_id=str(uuid.uuid4()),
                confirmed=True,
                step_up_valid=True,
            )
