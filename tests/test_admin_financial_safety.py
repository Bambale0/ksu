import random
import uuid
from decimal import Decimal

import pytest

from app.db.models import AdminAccount, Generation, Payment, User, Wallet
from app.db.payment_models import PaymentReversal
from app.db.session import SessionFactory
from app.services.admin_generation_operations import AdminGenerationOperationService
from app.services.admin_payments import AdminPaymentService
from app.services.admin_reporting import AdminReportingService
from app.services.payments import PaymentService
from app.services.wallet import WalletService


@pytest.mark.asyncio
async def test_completed_payment_reprocess_does_not_double_credit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(8_100_000_000_000, 8_199_999_999_999),
            first_name="Payment admin",
        )
        customer = User(
            telegram_id=random.randint(8_200_000_000_000, 8_299_999_999_999),
            first_name="Payment customer",
        )
        session.add_all([admin_user, customer])
        await session.flush()
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        payment = Payment(
            user_id=customer.id,
            provider="cryptopay",
            external_id=f"integration-{uuid.uuid4()}",
            amount=Decimal("500"),
            currency="RUB",
            rox_amount=Decimal("50"),
            status="succeeded",
            payload={"integration": True},
        )
        session.add_all([admin, payment])
        await session.flush()
        await WalletService.credit(
            session,
            user_id=customer.id,
            amount=Decimal("50"),
            kind="payment",
            reference_type="payment",
            reference_id=str(payment.id),
            idempotency_key=f"payment-credit:{payment.id}",
        )
        await session.commit()
        admin_id = admin.id
        payment_id = payment.id
        customer_id = customer.id

    async def fake_reconcile(session, *, payment_id):  # type: ignore[no-untyped-def]
        item = await session.get(Payment, payment_id)
        assert item is not None
        assert item.status == "succeeded"
        return item

    monkeypatch.setattr(PaymentService, "reconcile", fake_reconcile)

    async with SessionFactory() as session:
        admin = await session.get(AdminAccount, admin_id)
        assert admin is not None
        for suffix in ("one", "two"):
            result, _ = await AdminPaymentService.reprocess(
                session,
                admin=admin,
                payment_id=payment_id,
                idempotency_key=f"integration-payment-reprocess:{payment_id}:{suffix}",
                request_id=f"payment-reprocess-{suffix}",
                confirmed=True,
                step_up_valid=True,
            )
            assert result["status"] == "succeeded"
        await session.commit()

        wallet = await session.get(Wallet, customer_id)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("50.00")


@pytest.mark.asyncio
async def test_operation_refund_is_single_effect_even_with_new_idempotency_key() -> None:
    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(8_300_000_000_000, 8_399_999_999_999),
            first_name="Refund admin",
        )
        customer = User(
            telegram_id=random.randint(8_400_000_000_000, 8_499_999_999_999),
            first_name="Refund customer",
        )
        session.add_all([admin_user, customer])
        await session.flush()
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        generation = Generation(
            user_id=customer.id,
            kind="text_to_image",
            status="failed",
            prompt="refund integration",
            cost_rox=Decimal("15"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add_all([admin, generation])
        await session.flush()
        await WalletService.credit(
            session,
            user_id=customer.id,
            amount=Decimal("30"),
            kind="integration_seed",
            reference_type="integration",
            reference_id=str(customer.id),
            idempotency_key=f"integration-seed:{customer.id}",
        )
        await WalletService.debit(
            session,
            user_id=customer.id,
            amount=Decimal("15"),
            kind="generation_charge",
            reference_type="generation",
            reference_id=str(generation.id),
            idempotency_key=f"generation-charge:{generation.id}",
        )
        await session.commit()
        admin_id = admin.id
        generation_id = generation.id
        customer_id = customer.id

    async with SessionFactory() as session:
        admin = await session.get(AdminAccount, admin_id)
        assert admin is not None
        first, _ = await AdminGenerationOperationService.refund_operation(
            session,
            admin=admin,
            operation_id=generation_id,
            idempotency_key=f"integration-refund:{generation_id}:first",
            request_id="refund-first",
            confirmed=True,
            step_up_valid=True,
            reason="integration refund",
        )
        second, _ = await AdminGenerationOperationService.refund_operation(
            session,
            admin=admin,
            operation_id=generation_id,
            idempotency_key=f"integration-refund:{generation_id}:second",
            request_id="refund-second",
            confirmed=True,
            step_up_valid=True,
            reason="integration refund repeated",
        )
        await session.commit()

        assert first["status"] == "refunded"
        assert first["refunded_credits"] == "15.00"
        assert second["status"] == "already_refunded"
        wallet = await session.get(Wallet, customer_id)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("30.00")


@pytest.mark.asyncio
async def test_admin_summary_reports_net_money_after_full_refund() -> None:
    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(8_500_000_000_000, 8_599_999_999_999),
            first_name="Reporting admin",
        )
        customer = User(
            telegram_id=random.randint(8_600_000_000_000, 8_699_999_999_999),
            first_name="Reporting customer",
        )
        session.add_all([admin_user, customer])
        await session.flush()
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        session.add(admin)
        await session.flush()
        baseline = await AdminReportingService.summary(session, admin=admin)
        payment = Payment(
            user_id=customer.id,
            provider="reporting",
            external_id=f"reporting-{uuid.uuid4()}",
            amount=Decimal("100"),
            currency="RUB",
            rox_amount=Decimal("100"),
            status="refunded",
            payload={},
        )
        session.add(payment)
        await session.flush()
        session.add(
            PaymentReversal(
                payment_id=payment.id,
                provider=payment.provider,
                idempotency_key=f"reporting-reversal:{uuid.uuid4()}",
                amount=Decimal("100"),
                credits=Decimal("100"),
                reason="refund",
                provider_payload={},
            )
        )
        await WalletService.ensure_wallet(session, customer.id)
        await session.commit()

        summary = await AdminReportingService.summary(session, admin=admin)
        assert Decimal(summary["payments"]["gross_amount"]) - Decimal(
            baseline["payments"]["gross_amount"]
        ) == Decimal("100.00")
        assert Decimal(summary["payments"]["reversed_amount"]) - Decimal(
            baseline["payments"]["reversed_amount"]
        ) == Decimal("100.00")
        assert Decimal(summary["payments"]["net_amount"]) == Decimal(
            baseline["payments"]["net_amount"]
        )
