from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.admin_models import TariffVersion
from app.db.models import AdminAccount, User, Wallet, WalletTransaction
from app.db.prompt_tool_models import PromptToolOutbox, PromptToolTask
from app.db.session import SessionFactory
from app.services.prompt_tools import PromptToolPricingService, PromptToolService
from app.services.wallet import WalletService


@asynccontextmanager
async def _funded_user(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncSession, User]]:
    """Use the isolated CI database and remove only this test's own records."""
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    monkeypatch.setattr(settings, "neironych_api_key", "synthetic-qwen-primary-key")
    monkeypatch.setattr(settings, "nexus_api_key", "synthetic-nexus-prompt-key")
    async with SessionFactory() as session:
        user = User(
            telegram_id=uuid.uuid4().int % 10**14,
            first_name="Synthetic Qwen admission user",
        )
        admin_user = User(
            telegram_id=uuid.uuid4().int % 10**14,
            first_name="Synthetic Qwen tariff author",
        )
        session.add_all([user, admin_user])
        await session.flush()
        admin = AdminAccount(user_id=admin_user.id, role="admin", is_active=True)
        session.add(admin)
        await session.flush()
        latest_version = await session.scalar(select(func.max(TariffVersion.version)))
        tariff = TariffVersion(
            version=int(latest_version or 0) + 1,
            status="published",
            payload={
                "packages": [],
                "image_models": {},
                "video_models": {},
                "partner_rates": {},
                "prompt_costs": {
                    "image_analysis": "15.00",
                    "prompt_builder": "10.00",
                    "video_prompt": "30.00",
                },
            },
            created_by_admin_id=admin.id,
            published_by_admin_id=admin.id,
        )
        session.add(tariff)
        await WalletService.credit(
            session,
            user_id=user.id,
            amount=Decimal("100.00"),
            kind="test_seed",
            reference_type="test",
            reference_id=str(user.id),
            idempotency_key=f"qwen-primary-seed:{user.id}",
        )
        await session.commit()
        user_ids, tariff_id = [user.id, admin_user.id], tariff.id
        try:
            yield session, user
        finally:
            await session.rollback()
            await session.execute(delete(TariffVersion).where(TariffVersion.id == tariff_id))
            # User FKs cascade to this user's task/outbox and wallet ledger only.
            await session.execute(delete(User).where(User.id.in_(user_ids)))
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool", "payload", "cost"),
    [
        (
            "image_analysis",
            {"image_url": "https://synthetic.example.invalid/reference.jpg", "instruction": "Keep the light"},
            Decimal("1.00"),
        ),
        (
            "video_prompt",
            {
                "video_url": "https://synthetic.example.invalid/reference.mp4",
                "instruction": "Keep the camera movement",
                "duration_seconds": 10,
            },
            Decimal("30.00"),
        ),
    ],
    ids=["photo", "video"],
)
async def test_new_media_prompt_persists_qwen_primary_and_replays_one_charge(
    monkeypatch: pytest.MonkeyPatch,
    tool: str,
    payload: dict[str, object],
    cost: Decimal,
) -> None:
    async with _funded_user(monkeypatch) as (session, user):
        redis = AsyncMock()
        key = f"qwen-primary-{uuid.uuid4()}"
        first, first_replayed = await PromptToolService.create_task(
            session,
            redis,
            user_id=user.id,
            tool=tool,
            payload=payload,
            idempotency_key=key,
        )
        task_id, user_id = first.id, user.id
        first_route = (first.provider, first.model)

        # A fresh session proves that both route and replay identity were committed.
        async with SessionFactory() as replay_session:
            second, replayed = await PromptToolService.create_task(
                replay_session,
                redis,
                user_id=user_id,
                tool=tool,
                payload=payload,
                idempotency_key=key,
            )
            tasks = list(await replay_session.scalars(
                select(PromptToolTask).where(PromptToolTask.user_id == user_id)
            ))
            outboxes = list(await replay_session.scalars(
                select(PromptToolOutbox).where(PromptToolOutbox.task_id == task_id)
            ))
            debits = list(await replay_session.scalars(
                select(WalletTransaction).where(
                    WalletTransaction.user_id == user_id,
                    WalletTransaction.kind == "prompt_tool",
                )
            ))
            wallet = await replay_session.get(Wallet, user_id)

            assert first_replayed is False and replayed is True
            assert second.id == task_id
            assert len(tasks) == len(outboxes) == len(debits) == 1
            assert outboxes[0].status == "pending" and outboxes[0].attempts == 0
            assert second.status == "queued"
            assert Decimal(second.cost_credits) == cost
            assert Decimal(debits[0].amount) == -cost
            assert debits[0].reference_id == str(task_id)
            assert wallet is not None
            assert Decimal(wallet.balance) == Decimal("100.00") - cost
            assert (second.provider, second.model) == first_route
            assert second.provider == "neironych"
            assert second.model == "qwen3.8-max"


@pytest.mark.asyncio
async def test_prompt_catalog_advertises_qwen_for_photo_and_video_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _funded_user(monkeypatch) as (session, user):
        catalog = await PromptToolPricingService.catalog(session, user_id=user.id)
        items = {item["id"]: item for item in catalog["items"]}

        assert set(items) == {"image_analysis", "video_prompt", "prompt_builder"}
        assert all(item["enabled"] for item in items.values())
        assert items["image_analysis"]["cost_credits"] == "1.00"
        assert items["video_prompt"]["cost_credits"] == "30.00"
        assert items["prompt_builder"]["cost_credits"] == "1.00"
        assert items["prompt_builder"]["model"] == "gpt-5.5"
        assert items["image_analysis"]["model"] == "qwen3.8-max"
        assert items["video_prompt"]["model"] == "qwen3.8-max"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_url", "model"),
    [
        (None, "gpt-5.5"),
        ("https://synthetic.example.invalid/builder-reference.jpg", "gpt-6-sol"),
    ],
    ids=["text-only", "legacy-image-reference"],
)
async def test_prompt_builder_keeps_its_existing_nexus_route(
    monkeypatch: pytest.MonkeyPatch,
    image_url: str | None,
    model: str,
) -> None:
    async with _funded_user(monkeypatch) as (session, user):
        task, replayed = await PromptToolService.create_task(
            session,
            AsyncMock(),
            user_id=user.id,
            tool="prompt_builder",
            payload={"text": "A blue ceramic cup", "image_url": image_url},
            idempotency_key=f"qwen-builder-guard-{uuid.uuid4()}",
        )
        task_id, user_id = task.id, user.id
        async with SessionFactory() as read_session:
            stored = await read_session.get(PromptToolTask, task_id)
            wallet = await read_session.get(Wallet, user_id)
            assert replayed is False
            assert stored is not None
            assert stored.provider == "nexus" and stored.model == model
            assert Decimal(stored.cost_credits) == Decimal("1.00")
            assert wallet is not None
            assert Decimal(wallet.balance) == Decimal("99.00")
