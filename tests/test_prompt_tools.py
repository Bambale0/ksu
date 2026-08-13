from __future__ import annotations

import random
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.admin_models import TariffVersion
from app.db.models import AdminAccount, User, Wallet
from app.db.prompt_tool_models import PromptToolOutbox, PromptToolTask
from app.db.session import SessionFactory
from app.providers.kie_prompt_tools import PromptToolProviderError, PromptToolProviderResult
from app.services.prompt_tools import (
    PromptToolIdempotencyConflict,
    PromptToolOutboxService,
    PromptToolProcessor,
    PromptToolService,
)
from app.services.wallet import WalletService


async def _fixture_user_and_tariff(session) -> tuple[User, AdminAccount]:  # type: ignore[no-untyped-def]
    # These integration tests intentionally share one CI database. Keep the
    # prompt-tools queue isolated so a worker test never claims another test's
    # pending job.
    await session.execute(delete(PromptToolOutbox))
    await session.execute(delete(PromptToolTask))

    admin_user = User(
        telegram_id=random.randint(9_100_000_000_000, 9_199_999_999_999),
        first_name="Prompt tools admin",
    )
    user = User(
        telegram_id=random.randint(9_200_000_000_000, 9_299_999_999_999),
        first_name="Prompt tools user",
    )
    session.add_all([admin_user, user])
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
    tariff = TariffVersion(
        version=random.randint(20_000_000, 29_999_999),
        status="published",
        payload={
            "packages": [],
            "image_models": {},
            "video_models": {},
            "partner_rates": {},
            "prompt_costs": {
                "image_analysis": "2.00",
                "prompt_builder": "3.00",
            },
        },
        created_by_admin_id=admin.id,
        published_by_admin_id=admin.id,
    )
    session.add(tariff)
    await WalletService.credit(
        session,
        user_id=user.id,
        amount=Decimal("20.00"),
        kind="test_seed",
        reference_type="test",
        reference_id=str(user.id),
        idempotency_key=f"prompt-tools-seed:{user.id}",
    )
    await session.commit()
    return user, admin


@pytest.mark.asyncio
async def test_prompt_tool_create_is_idempotent_and_charges_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    async with SessionFactory() as session:
        user, _admin = await _fixture_user_and_tariff(session)
        redis = AsyncMock()
        key = f"prompt-tool-test-{uuid.uuid4()}"
        payload = {"text": "cinematic portrait", "image_url": None}

        first, replayed_first = await PromptToolService.create_task(
            session,
            redis,
            user_id=user.id,
            tool="prompt_builder",
            payload=payload,
            idempotency_key=key,
        )
        second, replayed_second = await PromptToolService.create_task(
            session,
            redis,
            user_id=user.id,
            tool="prompt_builder",
            payload=payload,
            idempotency_key=key,
        )

        wallet = await session.get(Wallet, user.id)
        assert replayed_first is False
        assert replayed_second is True
        assert first.id == second.id
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("17.00")
        outboxes = list(
            (
                await session.scalars(
                    select(PromptToolOutbox).where(PromptToolOutbox.task_id == first.id)
                )
            ).all()
        )
        assert len(outboxes) == 1

        with pytest.raises(PromptToolIdempotencyConflict):
            await PromptToolService.create_task(
                session,
                redis,
                user_id=user.id,
                tool="prompt_builder",
                payload={"text": "different request", "image_url": None},
                idempotency_key=key,
            )


@pytest.mark.asyncio
async def test_prompt_tool_worker_persists_structured_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        async def aclose(self) -> None:
            return None

        async def build_prompt(self, **_kwargs) -> PromptToolProviderResult:  # type: ignore[no-untyped-def]
            return PromptToolProviderResult(
                model="gpt-5-5",
                payload={"prompt_ru": "Русский промпт", "prompt_en": "English prompt"},
                credits_consumed=Decimal("0.1234"),
            )

    monkeypatch.setattr("app.services.prompt_tools.KiePromptToolsClient", FakeClient)

    async with SessionFactory() as session:
        user, _admin = await _fixture_user_and_tariff(session)
        task, _ = await PromptToolService.create_task(
            session,
            AsyncMock(),
            user_id=user.id,
            tool="prompt_builder",
            payload={"text": "portrait", "image_url": None},
            idempotency_key=f"prompt-success-{uuid.uuid4()}",
        )
        task_id = task.id
        claimed = await PromptToolOutboxService.claim(session)
        assert claimed is not None
        assert claimed.task_id == task_id
        await PromptToolProcessor.process(session, AsyncMock(), claimed)

        refreshed = await session.get(PromptToolTask, task_id)
        assert refreshed is not None
        assert refreshed.status == "succeeded"
        assert refreshed.result_payload == {
            "prompt_ru": "Русский промпт",
            "prompt_en": "English prompt",
        }
        assert Decimal(refreshed.provider_credits or 0) == Decimal("0.1234")


@pytest.mark.asyncio
async def test_terminal_provider_failure_refunds_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    monkeypatch.setattr(settings, "generation_submission_max_attempts", 1)

    class FailingClient:
        def __init__(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        async def aclose(self) -> None:
            return None

        async def analyze_image(self, **_kwargs) -> PromptToolProviderResult:  # type: ignore[no-untyped-def]
            raise PromptToolProviderError("provider unavailable")

    monkeypatch.setattr("app.services.prompt_tools.KiePromptToolsClient", FailingClient)

    async with SessionFactory() as session:
        user, _admin = await _fixture_user_and_tariff(session)
        task, _ = await PromptToolService.create_task(
            session,
            AsyncMock(),
            user_id=user.id,
            tool="image_analysis",
            payload={"image_url": "https://cdn.example.invalid/photo.jpg", "instruction": ""},
            idempotency_key=f"prompt-failure-{uuid.uuid4()}",
        )
        task_id = task.id
        wallet_after_charge = await session.get(Wallet, user.id)
        assert wallet_after_charge is not None
        assert Decimal(wallet_after_charge.balance) == Decimal("18.00")

        claimed = await PromptToolOutboxService.claim(session)
        assert claimed is not None
        assert claimed.task_id == task_id
        await PromptToolProcessor.process(session, AsyncMock(), claimed)

        refreshed = await session.get(PromptToolTask, task_id)
        wallet = await session.get(Wallet, user.id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert wallet is not None
        assert Decimal(wallet.balance) == Decimal("20.00")
