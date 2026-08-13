import json
import random
import uuid
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.db.admin_models import NotificationCampaignDelivery, SupportOutbox
from app.db.models import AdminAccount, Generation, SupportTicket, User, Wallet
from app.db.reliability_models import GenerationOutbox
from app.db.session import SessionFactory
from app.main import app
from app.services.admin_generation_operations import AdminGenerationOperationService
from app.services.admin_notifications import AdminNotificationService
from app.services.admin_support import AdminSupportService
from app.services.internal_admin_security import calculate_signature
from app.services.wallet import WalletService


@pytest.fixture(autouse=True)
def _configured_admin_audit_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "admin_security_key",
        "test-admin-security-key-0000000000000000000000000000",
    )


def _headers(
    *,
    secret: str,
    method: str,
    path: str,
    body: bytes,
    request_id: str,
    admin_user_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    confirmed: bool = False,
    step_up: bool = False,
    timestamp: int = 1_900_000_000,
) -> dict[str, str]:
    headers = {
        "X-Admin-Timestamp": str(timestamp),
        "X-Request-Id": request_id,
        "X-Admin-Signature": calculate_signature(
            secret,
            timestamp=timestamp,
            request_id=request_id,
            method=method,
            path=path,
            raw_body=body,
        ),
    }
    if body:
        headers["Content-Type"] = "application/json"
    if admin_user_id is not None:
        headers["X-Admin-User-Id"] = str(admin_user_id)
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    if confirmed:
        headers["X-Admin-Confirm"] = "confirmed"
    if step_up:
        headers["X-Admin-Step-Up"] = "confirmed"
    return headers


@pytest.mark.asyncio
async def test_signed_internal_admin_health_accepts_exact_body(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "integration-internal-admin-secret-000000000000"
    monkeypatch.setattr(settings, "internal_admin_hmac_secret", secret)
    monkeypatch.setattr(settings, "internal_admin_network_allowlist", "127.0.0.1/32")
    monkeypatch.setattr(settings, "internal_admin_timestamp_skew_seconds", 999_999_999)

    path = "/internal/admin/health"
    body = b""
    headers = _headers(
        secret=secret,
        method="GET",
        path=path,
        body=body,
        request_id="health-integration",
    )
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(path, headers=headers)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["request_id"] == "health-integration"


@pytest.mark.asyncio
async def test_signed_balance_adjustment_replays_same_idempotency_key_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "integration-balance-secret-000000000000000000"
    monkeypatch.setattr(settings, "internal_admin_hmac_secret", secret)
    monkeypatch.setattr(settings, "internal_admin_network_allowlist", "127.0.0.1/32")
    monkeypatch.setattr(settings, "internal_admin_timestamp_skew_seconds", 999_999_999)

    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(7_100_000_000_000, 7_199_999_999_999),
            first_name="Admin integration",
        )
        target_user = User(
            telegram_id=random.randint(7_200_000_000_000, 7_299_999_999_999),
            first_name="Target integration",
        )
        session.add_all([admin_user, target_user])
        await session.flush()
        admin = AdminAccount(
            user_id=admin_user.id,
            role="admin",
            permission_overrides={},
            is_active=True,
            mfa_enabled=True,
        )
        session.add(admin)
        await WalletService.ensure_wallet(session, target_user.id)
        await session.commit()
        admin_id = admin.id
        target_id = target_user.id

    path = f"/internal/admin/users/{target_id}/balance-adjustments"
    body = json.dumps(
        {"amount": "25", "reason": "integration balance topup"},
        separators=(",", ":"),
    ).encode()
    key = f"integration-balance:{uuid.uuid4()}"
    headers = _headers(
        secret=secret,
        method="POST",
        path=path,
        body=body,
        request_id="balance-integration",
        admin_user_id=admin_id,
        idempotency_key=key,
        confirmed=True,
        step_up=True,
    )
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(path, headers=headers, content=body)
        second = await client.post(path, headers=headers, content=body)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["balance_after"] == "25.00"
    assert first.json()["idempotency_replayed"] is False
    assert second.json()["balance_after"] == "25.00"
    assert second.json()["idempotency_replayed"] is True

    async with SessionFactory() as session:
        wallet = await session.get(Wallet, target_id)
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("25.00")


@pytest.mark.asyncio
async def test_support_reply_creates_outbox_instead_of_request_side_send() -> None:
    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(7_300_000_000_000, 7_399_999_999_999),
            first_name="Support admin",
        )
        customer = User(
            telegram_id=random.randint(7_400_000_000_000, 7_499_999_999_999),
            first_name="Support customer",
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
        ticket = SupportTicket(user_id=customer.id, topic="integration support", status="open")
        session.add_all([admin, ticket])
        await session.flush()

        result, replayed = await AdminSupportService.reply_ticket(
            session,
            admin=admin,
            ticket_id=ticket.id,
            body="Durable operator response",
            idempotency_key=f"integration-support:{uuid.uuid4()}",
            request_id="support-integration",
            confirmed=True,
        )
        await session.commit()

        assert replayed is False
        outbox = await session.get(SupportOutbox, uuid.UUID(result["outbox_id"]))
        assert outbox is not None
        assert outbox.status == "pending"
        assert result["delivery_status"] == "pending"


@pytest.mark.asyncio
async def test_campaign_start_materializes_recipients_once() -> None:
    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(7_500_000_000_000, 7_599_999_999_999),
            first_name="Campaign admin",
        )
        recipient_a = User(
            telegram_id=random.randint(7_600_000_000_000, 7_649_999_999_999),
            first_name="Campaign A",
        )
        recipient_b = User(
            telegram_id=random.randint(7_650_000_000_000, 7_699_999_999_999),
            first_name="Campaign B",
        )
        session.add_all([admin_user, recipient_a, recipient_b])
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

        create_result, _ = await AdminNotificationService.create_campaign(
            session,
            admin=admin,
            name="Integration campaign",
            segment={
                "active_only": True,
                "user_ids": [str(recipient_a.id), str(recipient_b.id)],
            },
            message={"title": "Integration", "body": "Durable campaign"},
            idempotency_key=f"integration-campaign-create:{uuid.uuid4()}",
            request_id="campaign-create-integration",
        )
        campaign_id = uuid.UUID(create_result["id"])
        start_key = f"integration-campaign-start:{uuid.uuid4()}"
        first, first_replayed = await AdminNotificationService.start_campaign(
            session,
            admin=admin,
            campaign_id=campaign_id,
            idempotency_key=start_key,
            request_id="campaign-start-integration",
            confirmed=True,
            step_up_valid=True,
        )
        second, second_replayed = await AdminNotificationService.start_campaign(
            session,
            admin=admin,
            campaign_id=campaign_id,
            idempotency_key=start_key,
            request_id="campaign-start-integration-repeat",
            confirmed=True,
            step_up_valid=True,
        )
        await session.commit()

        delivery_count = int(
            (
                await session.scalar(
                    select(func.count())
                    .select_from(NotificationCampaignDelivery)
                    .where(NotificationCampaignDelivery.campaign_id == campaign_id)
                )
            )
            or 0
        )
        assert first_replayed is False
        assert second_replayed is True
        assert first["total_deliveries"] == 2
        assert second["total_deliveries"] == 2
        assert delivery_count == 2


@pytest.mark.asyncio
async def test_operation_replay_creates_zero_cost_child_and_outbox() -> None:
    async with SessionFactory() as session:
        admin_user = User(
            telegram_id=random.randint(7_700_000_000_000, 7_799_999_999_999),
            first_name="Replay admin",
        )
        customer = User(
            telegram_id=random.randint(7_800_000_000_000, 7_899_999_999_999),
            first_name="Replay customer",
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
        source = Generation(
            user_id=customer.id,
            kind="text_to_image",
            status="failed",
            prompt="original generation",
            cost_rox=Decimal("15"),
            provider="kie",
            parameters={"_model_id": "nano-banana"},
        )
        session.add_all([admin, source])
        await session.flush()

        result, replayed = await AdminGenerationOperationService.replay_operation(
            session,
            admin=admin,
            operation_id=source.id,
            idempotency_key=f"integration-replay:{uuid.uuid4()}",
            request_id="operation-replay-integration",
            confirmed=True,
            step_up_valid=True,
        )
        await session.commit()

        child_id = uuid.UUID(result["child_operation_id"])
        child = await session.get(Generation, child_id)
        outbox = await session.scalar(
            select(GenerationOutbox).where(GenerationOutbox.generation_id == child_id)
        )
        assert replayed is False
        assert child is not None
        assert Decimal(child.cost_rox) == Decimal("0")
        assert child.parameters["_admin_replay_of"] == str(source.id)
        assert outbox is not None
        assert outbox.status == "pending"