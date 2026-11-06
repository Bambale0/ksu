from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.api.admin_deps import AdminContext, get_admin_context_base
from app.core.config import settings
from app.db.admin_models import AdminCommand
from app.db.models import (
    AdminAccount,
    AdminAuditLog,
    AdminSession,
    Payment,
    User,
    Wallet,
    WalletTransaction,
)
from app.db.session import SessionFactory
from app.main import app
from app.providers.payment_2328 import Payment2328Client
from app.services.admin_security import utcnow


@pytest.fixture
async def payment_admin(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AdminContext]:
    monkeypatch.setattr(
        settings, "admin_security_key", "synthetic-payment-admin-key-000000000000000000",
    )
    monkeypatch.setattr(settings, "payment_2328_project_uuid", "synthetic-test-project")
    monkeypatch.setattr(settings, "payment_2328_api_key", "synthetic-test-key")
    async with SessionFactory() as session:
        actor = User(
            telegram_id=uuid.uuid4().int % 10**14, first_name="Synthetic payment admin",
        )
        session.add(actor)
        await session.flush()
        admin = AdminAccount(
            user_id=actor.id, role="admin", is_active=True,
            mfa_enabled=True, permission_overrides={},
        )
        session.add(admin)
        await session.flush()
        now = utcnow()
        admin_session = AdminSession(
            admin_id=admin.id, token_hash=uuid.uuid4().hex,
            created_at=now, last_seen_at=now,
            expires_at=now + timedelta(hours=1),
            idle_expires_at=now + timedelta(hours=1),
            mfa_verified=True, step_up_until=now + timedelta(minutes=5),
            session_version=admin.session_version,
        )
        session.add(admin_session)
        await session.commit()
        context = AdminContext(account=admin, session=admin_session, user=actor)

    async def authenticated_context() -> AdminContext:
        return context

    monkeypatch.setitem(
        app.dependency_overrides, get_admin_context_base, authenticated_context,
    )
    yield context


async def _pending_crypto_payment() -> Payment:
    async with SessionFactory() as session:
        customer = User(
            telegram_id=uuid.uuid4().int % 10**14, first_name="Synthetic crypto customer",
        )
        session.add(customer)
        await session.flush()
        payment = Payment(
            user_id=customer.id,
            provider="2328",
            external_id=str(uuid.uuid4()),
            amount=Decimal("54.35"),
            currency="RUB",
            rox_amount=Decimal("50"),
            status="pending",
            payload={},
        )
        session.add(payment)
        await session.commit()
        return payment


def _path(action: str, payment: Payment) -> str:
    if action == "reconcile":
        return f"/api/v1/admin/payments/{payment.id}/reconcile"
    return f"/api/v1/admin/control/payments/{payment.id}/{action}"


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4()), "X-Admin-Confirm": "confirmed"}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["recheck", "reprocess", "reconcile"])
async def test_admin_crypto_reconciliation_credits_once_through_2328_provider(
    monkeypatch: pytest.MonkeyPatch,
    payment_admin: AdminContext,
    action: str,
) -> None:
    payment = await _pending_crypto_payment()
    calls = 0

    async def get_payment_info(
        self: Payment2328Client,
        *,
        external_id: str | None = None,
        order_id: str | None = None,
    ) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        assert external_id == payment.external_id
        assert order_id is None
        return {
            "uuid": payment.external_id,
            "order_id": str(payment.id),
            "amount": "54.35000000",
            "currency": "RUB",
            "payment_status": "paid",
        }

    monkeypatch.setattr(Payment2328Client, "get_payment_info", get_payment_info)
    headers = _headers()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        first = await client.post(_path(action, payment), headers=headers)
        assert first.status_code == 200, first.text
        assert first.json()["provider"] == "2328"
        assert first.json()["status"] == "succeeded"
        replay = await client.post(_path(action, payment), headers=headers)
        assert replay.status_code == 200, replay.text
        if action != "reconcile":
            assert first.json()["idempotency_replayed"] is False
            assert replay.json()["idempotency_replayed"] is True
            assert calls == 1
        repeated = await client.post(_path(action, payment), headers=_headers())
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["status"] == "succeeded"

    async with SessionFactory() as session:
        saved = await session.get(Payment, payment.id)
        wallet = await session.get(Wallet, payment.user_id)
        transactions = list((await session.scalars(
            select(WalletTransaction).where(WalletTransaction.user_id == payment.user_id),
        )).all())
        assert saved is not None and saved.status == "succeeded"
        assert wallet is not None and wallet.balance == Decimal("50")
        assert len(transactions) == 1
        assert transactions[0].idempotency_key == f"payment:{payment.id}:credit"
        assert transactions[0].reference_id == str(payment.id)
        if action == "reconcile":
            audits = list((await session.scalars(
                select(AdminAuditLog).where(
                    AdminAuditLog.resource_id == str(payment.id),
                    AdminAuditLog.action == "admin.payment.reconciled",
                ),
            )).all())
            assert len(audits) == 3
            assert all(row.admin_id == payment_admin.account.id for row in audits)
        else:
            command = await session.scalar(
                select(AdminCommand).where(
                    AdminCommand.idempotency_key == headers["Idempotency-Key"],
                ),
            )
            assert command is not None and command.status == "completed"
            assert command.action == f"payments.{action}"
            assert command.target_id == str(payment.id)
            assert command.admin_user_id == payment_admin.account.id


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["recheck", "reprocess", "reconcile"])
async def test_admin_crypto_reconciliation_enforces_current_permissions(
    monkeypatch: pytest.MonkeyPatch,
    payment_admin: AdminContext,
    action: str,
) -> None:
    payment = await _pending_crypto_payment()
    payment_admin.account.permission_overrides = {
        "deny": ["payments.read", "payments.manage", "users.wallet.adjust"],
    }

    async def unexpected_provider_call(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Denied payment command must not call the provider")

    monkeypatch.setattr(Payment2328Client, "get_payment_info", unexpected_provider_call)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post(_path(action, payment), headers=_headers())
    assert response.status_code == 403, response.text
    async with SessionFactory() as session:
        assert await session.get(Wallet, payment.user_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["reprocess", "reconcile"])
async def test_admin_crypto_financial_commands_require_fresh_mfa(
    monkeypatch: pytest.MonkeyPatch,
    payment_admin: AdminContext,
    action: str,
) -> None:
    payment = await _pending_crypto_payment()
    payment_admin.session.step_up_until = None

    async def unexpected_provider_call(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Financial command without fresh MFA must not call the provider")

    monkeypatch.setattr(Payment2328Client, "get_payment_info", unexpected_provider_call)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        response = await client.post(_path(action, payment), headers=_headers())
    assert response.status_code == 403, response.text
    assert "MFA" in response.json()["detail"]
    async with SessionFactory() as session:
        assert await session.get(Wallet, payment.user_id) is None
