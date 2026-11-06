"""The automatic worker and admin action must share one generation refund effect."""
from __future__ import annotations

import asyncio
import random
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import AdminAccount, Generation, User, Wallet, WalletTransaction
from app.db.session import SessionFactory
from app.services.admin_generation_operations import AdminGenerationOperationService
from app.services.generation_provider import GenerationProviderService
from app.services.wallet import WalletService


async def _charged_generation(*, charged: bool = True) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with SessionFactory() as session:
        customer = User(
            telegram_id=random.randint(8_710_000_000_000, 8_719_999_999_999),
            first_name="Refund boundary customer",
        )
        operator = User(
            telegram_id=random.randint(8_720_000_000_000, 8_729_999_999_999),
            first_name="Refund boundary operator",
        )
        session.add_all([customer, operator])
        await session.flush()
        admin = AdminAccount(
            user_id=operator.id,
            role="admin",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        generation = Generation(
            user_id=customer.id,
            kind="text_to_image",
            status="generating",
            prompt="Synthetic refund boundary test",
            cost_rox=Decimal("25") if charged else Decimal("0"),
            provider="kie",
            parameters={"_model_id": "nano-banana-pro"},
        )
        session.add_all([admin, generation])
        await session.flush()
        await WalletService.credit(
            session,
            user_id=customer.id,
            amount=Decimal("100"),
            kind="test_seed",
            idempotency_key=f"test-seed:{customer.id}",
        )
        if charged:
            await WalletService.debit(
                session,
                user_id=customer.id,
                amount=Decimal("25"),
                kind="generation",
                reference_type="generation",
                reference_id=str(generation.id),
                idempotency_key=f"generation:{generation.id}:charge",
            )
        await session.commit()
        return customer.id, admin.id, generation.id


async def _admin_refund(admin_id: uuid.UUID, generation_id: uuid.UUID) -> dict[str, object]:
    async with SessionFactory() as session:
        admin = await session.get(AdminAccount, admin_id)
        assert admin is not None
        result, _ = await AdminGenerationOperationService.refund_operation(
            session,
            admin=admin,
            operation_id=generation_id,
            idempotency_key=f"test-admin-refund:{uuid.uuid4()}",
            request_id=f"refund-boundary-{uuid.uuid4()}",
            confirmed=True,
            step_up_valid=True,
            reason="Synthetic confirmed refund",
        )
        await session.commit()
        return result


async def _automatic_refund(generation_id: uuid.UUID) -> None:
    async with SessionFactory() as session:
        await GenerationProviderService.fail_and_refund(
            session, generation_id, "Synthetic terminal provider failure"
        )


async def _assert_refund_effect(
    customer_id: uuid.UUID, generation_id: uuid.UUID, *, expected_refunds: int = 1
) -> None:
    async with SessionFactory() as session:
        wallet = await session.get(Wallet, customer_id)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("100.00")
        refunds = list(
            (
                await session.scalars(
                    select(WalletTransaction).where(
                        WalletTransaction.user_id == customer_id,
                        WalletTransaction.reference_id == str(generation_id),
                        WalletTransaction.reference_type.in_(["generation", "generation_refund"]),
                        WalletTransaction.kind.in_(["generation_refund", "generation_admin_refund"]),
                        WalletTransaction.amount > 0,
                    )
                )
            ).all()
        )
        assert len(refunds) == expected_refunds


@pytest.mark.asyncio
async def test_admin_refund_recognizes_previous_automatic_refund() -> None:
    customer_id, admin_id, generation_id = await _charged_generation()
    await _automatic_refund(generation_id)

    result = await _admin_refund(admin_id, generation_id)

    assert result["status"] == "already_refunded"
    assert Decimal(str(result["refunded_credits"])) == Decimal("25")
    await _assert_refund_effect(customer_id, generation_id)


@pytest.mark.asyncio
async def test_worker_failure_after_admin_refund_does_not_credit_twice() -> None:
    customer_id, admin_id, generation_id = await _charged_generation()
    result = await _admin_refund(admin_id, generation_id)
    assert result["status"] == "refunded"

    await _automatic_refund(generation_id)

    await _assert_refund_effect(customer_id, generation_id)
    async with SessionFactory() as session:
        generation = await session.get(Generation, generation_id)
        assert generation is not None and generation.status == "failed"


@pytest.mark.asyncio
async def test_worker_recognizes_legacy_admin_refund_shape() -> None:
    customer_id, _, generation_id = await _charged_generation()
    async with SessionFactory() as session:
        await WalletService.credit(
            session,
            user_id=customer_id,
            amount=Decimal("25"),
            kind="generation_admin_refund",
            reference_type="generation_refund",
            reference_id=str(generation_id),
            idempotency_key=f"admin-operation-refund:{generation_id}",
        )
        await session.commit()

    await _automatic_refund(generation_id)

    await _assert_refund_effect(customer_id, generation_id)


@pytest.mark.asyncio
async def test_concurrent_admin_and_worker_refunds_have_one_effect() -> None:
    customer_id, admin_id, generation_id = await _charged_generation()

    await asyncio.gather(
        _admin_refund(admin_id, generation_id),
        _automatic_refund(generation_id),
    )

    await _assert_refund_effect(customer_id, generation_id)


@pytest.mark.asyncio
async def test_concurrent_admin_commands_return_one_existing_refund() -> None:
    customer_id, admin_id, generation_id = await _charged_generation()

    results = await asyncio.gather(
        _admin_refund(admin_id, generation_id),
        _admin_refund(admin_id, generation_id),
    )

    assert sorted(result["status"] for result in results) == ["already_refunded", "refunded"]
    await _assert_refund_effect(customer_id, generation_id)


@pytest.mark.asyncio
async def test_free_admin_replay_has_no_refund() -> None:
    customer_id, admin_id, generation_id = await _charged_generation(charged=False)

    result = await _admin_refund(admin_id, generation_id)
    await _automatic_refund(generation_id)

    assert result["status"] == "no_charge"
    await _assert_refund_effect(customer_id, generation_id, expected_refunds=0)
