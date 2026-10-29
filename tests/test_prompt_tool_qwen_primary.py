from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.admin_models import AdminRuntimeSetting, TariffVersion
from app.db.models import AdminAccount, Notification, User, Wallet, WalletTransaction
from app.db.notification_models import NotificationDelivery
from app.db.prompt_tool_models import PromptToolOutbox, PromptToolTask
from app.db.session import SessionFactory
from app.providers.kie_prompt_tools import PromptToolProviderResult
from app.providers.neironych_errors import NeironychProviderError
from app.services import prompt_tool_routing
from app.services.abuse_protection import ProtectionBackendUnavailable, ResourceLimitExceeded
from app.services.prompt_tools import (
    ClaimedPromptTool,
    PromptToolOutboxService,
    PromptToolPricingService,
    PromptToolProcessor,
    PromptToolService,
)
from app.services.wallet import WalletService


@asynccontextmanager
async def _funded_user(
    monkeypatch: pytest.MonkeyPatch,
    *,
    isolate_queue: bool = False,
) -> AsyncIterator[tuple[AsyncSession, User, AdminAccount]]:
    """Use the isolated CI database and remove only this test's own records."""
    monkeypatch.setattr(settings, "abuse_protection_enabled", False)
    monkeypatch.setattr(settings, "neironych_api_key", "synthetic-qwen-primary-key")
    monkeypatch.setattr(settings, "nexus_api_key", "synthetic-nexus-prompt-key")
    policy_key = f"qwen-primary-test-{uuid.uuid4()}"
    monkeypatch.setattr(prompt_tool_routing, "PROMPT_TOOL_ROUTES_SETTING_KEY", policy_key)
    async with SessionFactory() as session:
        if isolate_queue:
            # Match existing worker fixtures: the CI database has one shared queue.
            await session.execute(delete(PromptToolOutbox))
            await session.execute(delete(PromptToolTask))
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
            yield session, user, admin
        finally:
            await session.rollback()
            await session.execute(delete(AdminRuntimeSetting).where(AdminRuntimeSetting.key == policy_key))
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
    async with _funded_user(monkeypatch) as (session, user, _admin):
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
    async with _funded_user(monkeypatch) as (session, user, _admin):
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
    async with _funded_user(monkeypatch) as (session, user, _admin):
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


def _media_input(tool: str) -> dict[str, object]:
    if tool == "image_analysis":
        return {"image_url": "https://synthetic.example.invalid/reference.jpg", "instruction": "Keep the light"}
    return {
        "video_url": "https://synthetic.example.invalid/reference.mp4",
        "instruction": "Keep the camera movement",
        "duration_seconds": 10,
    }


async def _create_media(
    session: AsyncSession, user: User, tool: str,
) -> tuple[PromptToolTask, str]:
    key = f"qwen-worker-{uuid.uuid4()}"
    task, replayed = await PromptToolService.create_task(
        session, AsyncMock(), user_id=user.id, tool=tool,
        payload=_media_input(tool), idempotency_key=key,
    )
    assert replayed is False
    return task, key


async def _claim(session: AsyncSession, task_id: uuid.UUID) -> ClaimedPromptTool:
    claimed = await PromptToolOutboxService.claim(session)
    assert claimed is not None and claimed.task_id == task_id
    return claimed


class _QwenProbe:
    """Provider boundary fake; all snapshots, leases and effects use PostgreSQL."""

    def __init__(self) -> None:
        self.prepared: list[dict[str, object]] = []
        self.submitted: list[dict[str, object]] = []
        self.snapshots: list[dict[str, object]] = []
        self.failures: list[Exception] = []
        self.preparer_changed = False
        self.nexus_calls = 0

    async def aclose(self) -> None:
        return None

    def _prepare(self, tool: str, model: str, source: str, instruction: str) -> str:
        assert not self.preparer_changed, "A retry must reuse the saved body without preparing media again"
        self.prepared.append({"tool": tool, "model": model, "source": source})
        return json.dumps({
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {
                    "url": source if tool == "image_analysis" else "data:image/jpeg;base64,c3ludGhldGlj",
                }},
            ]}],
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    async def prepare_image_request(
        self, *, image_url: str, instruction: str = "", model: str = "qwen3.8-max",
    ) -> str:
        return self._prepare("image_analysis", model, image_url, instruction)

    async def prepare_video_request(
        self, *, video_url: str, instruction: str = "", duration_seconds: int | None = None,
        model: str = "qwen3.8-max",
    ) -> str:
        assert duration_seconds == 10
        return self._prepare("video_prompt", model, video_url, instruction)

    async def submit(
        self, *, request_body: str, task_id: uuid.UUID, tool: str, model: str,
    ) -> PromptToolProviderResult:
        async with SessionFactory() as session:
            task = await session.get(PromptToolTask, task_id)
            assert task is not None and task.status == "processing"
            assert (task.provider, task.model) == ("neironych", model)
            snapshot = dict(task.input_payload["_qwen_submission"])
            assert snapshot["body_json"] == request_body
            assert snapshot["sha256"] == hashlib.sha256(request_body.encode()).hexdigest()
            assert snapshot["model"] == model
            assert snapshot["base_url"] == settings.neironych_api_base_url.rstrip("/")
            assert snapshot["client_request_id"] == str(task_id)
            media_kind = "photo" if tool == "image_analysis" else "video"
            assert snapshot["idempotency_key"] == f"ksu-prompt-{media_kind}-qwen38-{task_id}"
            self.snapshots.append(snapshot)
        self.submitted.append({"body": request_body, "task_id": task_id, "tool": tool, "model": model})
        if self.failures:
            raise self.failures.pop(0)
        return PromptToolProviderResult(
            model=model,
            payload={
                "prompt_ru": "Синтетический полный промпт",
                "prompt_en": "Synthetic complete prompt",
                "camera_movement_ru": "Плавное приближение",
                "timeline_ru": ["Общий план", "Крупный план"],
                "negative_prompt": "flicker, distortion",
            },
            credits_consumed=None,
        )


def _install_qwen_probe(monkeypatch: pytest.MonkeyPatch) -> _QwenProbe:
    probe = _QwenProbe()
    monkeypatch.setattr(
        "app.services.prompt_tool_execution.NeironychQwenPromptToolsClient", lambda *_args, **_kwargs: probe,
    )

    def forbidden_nexus(*_args, **_kwargs):
        probe.nexus_calls += 1
        raise AssertionError("This task must not submit to Nexus")

    monkeypatch.setattr("app.services.prompt_tool_execution.NexusPromptToolsClient", forbidden_nexus)
    return probe


async def _assert_single_wallet_effect(
    session: AsyncSession, *, user_id: uuid.UUID, task_id: uuid.UUID,
    cost: Decimal, refunded: bool = False,
) -> None:
    transactions = list(await session.scalars(select(WalletTransaction).where(
        WalletTransaction.user_id == user_id,
        WalletTransaction.reference_type == "prompt_tool_task",
        WalletTransaction.reference_id == str(task_id),
    )))
    debits = [row for row in transactions if row.kind == "prompt_tool"]
    refunds = [row for row in transactions if row.kind == "prompt_tool_refund"]
    assert len(debits) == 1 and Decimal(debits[0].amount) == -cost
    assert len(refunds) == int(refunded)
    if refunded:
        assert Decimal(refunds[0].amount) == cost
    wallet = await session.get(Wallet, user_id, populate_existing=True)
    assert wallet is not None
    assert Decimal(wallet.balance) == Decimal("100.00") - (Decimal("0") if refunded else cost)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["image_analysis", "video_prompt"], ids=["photo", "video"])
async def test_managed_qwen_success_commits_request_before_post_and_notifies_once(
    monkeypatch: pytest.MonkeyPatch, tool: str,
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, _admin):
        probe = _install_qwen_probe(monkeypatch)
        task, _key = await _create_media(session, user, tool)
        task_id, user_id = task.id, user.id
        claimed = await _claim(session, task_id)
        await PromptToolProcessor.process(session, AsyncMock(), claimed)
        await PromptToolProcessor.process(session, AsyncMock(), claimed)

        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        outbox = await session.get(PromptToolOutbox, claimed.outbox_id, populate_existing=True)
        assert stored is not None and stored.status == "succeeded"
        assert (stored.provider, stored.model) == ("neironych", "qwen3.8-max")
        assert stored.result_payload["prompt_ru"] == "Синтетический полный промпт"
        if tool == "video_prompt":
            assert stored.result_payload["camera_movement_ru"] == "Плавное приближение"
            assert stored.result_payload["timeline_ru"] == ["Общий план", "Крупный план"]
        assert outbox is not None and outbox.status == "completed"
        assert len(probe.prepared) == len(probe.submitted) == 1
        assert probe.nexus_calls == 0
        cost = Decimal("1.00") if tool == "image_analysis" else Decimal("30.00")
        await _assert_single_wallet_effect(session, user_id=user_id, task_id=task_id, cost=cost)
        notifications = list(await session.scalars(select(Notification).where(Notification.user_id == user_id)))
        assert len(notifications) == 1
        expected_kind = "prompt_tool_photo_succeeded" if tool == "image_analysis" else "prompt_tool_video_succeeded"
        assert notifications[0].kind == expected_kind
        assert notifications[0].body == stored.result_payload["prompt_ru"]
        deliveries = list(await session.scalars(select(NotificationDelivery).where(
            NotificationDelivery.notification_id == notifications[0].id,
        )))
        assert len(deliveries) == 1 and deliveries[0].status == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["image_analysis", "video_prompt"], ids=["photo", "video"])
async def test_runtime_policy_change_preserves_accepted_qwen_route_and_idempotent_replay(
    monkeypatch: pytest.MonkeyPatch, tool: str,
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, admin):
        probe = _install_qwen_probe(monkeypatch)
        task, key = await _create_media(session, user, tool)
        original_route = json.loads(json.dumps(task.input_payload["_prompt_tool_route"]))
        original_revision = task.input_payload["_prompt_tool_route_revision"]
        policy = await prompt_tool_routing.configured_prompt_tool_routes(session)
        policy["routes"][tool] = [{"provider": "nexus", "model": "gpt-6-sol"}]
        session.add(AdminRuntimeSetting(
            key=prompt_tool_routing.PROMPT_TOOL_ROUTES_SETTING_KEY,
            value={"revision": policy["revision"] + 1, "routes": policy["routes"]},
            updated_by_admin_id=admin.id,
        ))
        await session.commit()
        task_id, user_id = task.id, user.id

        async with SessionFactory() as other:
            replay, replayed = await PromptToolService.create_task(
                other, AsyncMock(), user_id=user_id, tool=tool,
                payload=_media_input(tool), idempotency_key=key,
            )
            next_task, _ = await PromptToolService.create_task(
                other, AsyncMock(), user_id=user_id, tool=tool,
                payload=_media_input(tool), idempotency_key=f"qwen-after-policy-{uuid.uuid4()}",
            )
            assert replayed is True and replay.id == task_id
            assert (replay.provider, replay.model) == ("neironych", "qwen3.8-max")
            assert replay.input_payload["_prompt_tool_route"] == original_route
            assert replay.input_payload["_prompt_tool_route_revision"] == original_revision
            assert replay.input_payload["_prompt_tool_route_index"] == 0
            assert (next_task.provider, next_task.model) == ("nexus", "gpt-6-sol")
            assert next_task.input_payload["_prompt_tool_route_revision"] == original_revision + 1

        claimed = await _claim(session, task_id)
        await PromptToolProcessor.process(session, AsyncMock(), claimed)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        assert stored is not None and stored.status == "succeeded"
        assert stored.input_payload["_prompt_tool_route"] == original_route
        assert probe.nexus_calls == 0 and len(probe.submitted) == 1
        charges = list(await session.scalars(select(WalletTransaction).where(
            WalletTransaction.user_id == user_id, WalletTransaction.kind == "prompt_tool",
        )))
        assert len(charges) == 2


@pytest.mark.asyncio
async def test_reclaimed_qwen_attempt_blocks_stale_worker_before_preparation_or_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, _admin):
        probe = _install_qwen_probe(monkeypatch)
        task, _key = await _create_media(session, user, "image_analysis")
        task_id = task.id
        stale = await _claim(session, task_id)
        row = await session.get(PromptToolOutbox, stale.outbox_id)
        assert row is not None
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        current = await _claim(session, task_id)
        assert current.attempts == stale.attempts + 1

        await PromptToolProcessor.process(session, AsyncMock(), stale)
        assert probe.prepared == [] and probe.submitted == [] and probe.nexus_calls == 0
        await PromptToolProcessor.process(session, AsyncMock(), current)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        assert stored is not None and stored.status == "succeeded"
        assert len(probe.prepared) == len(probe.submitted) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(None, "submission_outcome_unknown"), (503, "provider_temporarily_unavailable"),
     (409, "request_already_submitted")],
    ids=["timeout", "unverified-gateway-error", "in-progress-replay"],
)
async def test_qwen_uncertain_outcome_recovers_same_saved_video_body_without_preparing_again(
    monkeypatch: pytest.MonkeyPatch, status_code: int | None, error_code: str,
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, _admin):
        probe = _install_qwen_probe(monkeypatch)
        failure = NeironychProviderError(
            "Synthetic uncertain response", status_code=status_code, error_code=error_code,
        )
        if status_code is None:
            failure.__cause__ = httpx.ReadTimeout("Synthetic accepted response was lost")
        probe.failures.append(failure)
        task, _key = await _create_media(session, user, "video_prompt")
        task_id, user_id = task.id, user.id
        first = await _claim(session, task_id)
        await PromptToolProcessor.process(session, AsyncMock(), first)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        row = await session.get(PromptToolOutbox, first.outbox_id, populate_existing=True)
        assert stored is not None and stored.status == "queued"
        assert stored.provider == "neironych" and stored.input_payload["_prompt_tool_route_index"] == 0
        assert row is not None and row.status == "pending"
        await _assert_single_wallet_effect(session, user_id=user_id, task_id=task_id, cost=Decimal("30.00"))
        snapshot = dict(stored.input_payload["_qwen_submission"])
        probe.preparer_changed = True
        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

        retry = await _claim(session, task_id)
        assert retry.attempts == first.attempts + 1
        await PromptToolProcessor.process(session, AsyncMock(), retry)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        assert stored is not None and stored.status == "succeeded"
        assert stored.input_payload["_qwen_submission"] == snapshot
        assert len(probe.prepared) == 1 and len(probe.submitted) == 2
        assert probe.submitted[0] == probe.submitted[1]
        assert probe.snapshots[0]["idempotency_key"] == probe.snapshots[1]["idempotency_key"]
        assert probe.nexus_calls == 0
        await _assert_single_wallet_effect(session, user_id=user_id, task_id=task_id, cost=Decimal("30.00"))
        notifications = list(await session.scalars(select(Notification).where(Notification.user_id == user_id)))
        assert len(notifications) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [(413, "provider_rejected_request"), (422, "invalid_request_contract"),
     (403, "content_moderation"), (None, "prompt_response_invalid")],
    ids=["oversized", "invalid-input", "moderation", "invalid-output"],
)
async def test_permanent_qwen_failure_refunds_once_without_alternate_submission(
    monkeypatch: pytest.MonkeyPatch, status_code: int | None, error_code: str,
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, _admin):
        probe = _install_qwen_probe(monkeypatch)
        probe.failures.append(NeironychProviderError(
            "Synthetic permanent failure", status_code=status_code, error_code=error_code,
        ))
        task, _key = await _create_media(session, user, "image_analysis")
        task_id, user_id = task.id, user.id
        claimed = await _claim(session, task_id)
        await PromptToolProcessor.process(session, AsyncMock(), claimed)
        await PromptToolProcessor.process(session, AsyncMock(), claimed)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        outbox = await session.get(PromptToolOutbox, claimed.outbox_id, populate_existing=True)
        assert stored is not None and stored.status == "failed"
        assert stored.provider == "neironych" and stored.input_payload["_prompt_tool_route_index"] == 0
        assert outbox is not None and outbox.status == "failed"
        assert len(probe.submitted) == 1 and probe.nexus_calls == 0
        await _assert_single_wallet_effect(
            session, user_id=user_id, task_id=task_id, cost=Decimal("1.00"), refunded=True,
        )
        notifications = list(await session.scalars(select(Notification).where(Notification.user_id == user_id)))
        assert notifications == []


@pytest.mark.asyncio
async def test_verified_qwen_nonacceptance_persists_nexus_fallback_before_its_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, _admin):
        probe = _install_qwen_probe(monkeypatch)
        probe.failures.append(NeironychProviderError(
            "Synthetic verified nonacceptance", status_code=503,
            error_code="provider_temporarily_unavailable", submission_rejected=True,
        ))
        task, _key = await _create_media(session, user, "image_analysis")
        task_id, user_id = task.id, user.id
        nexus_calls = []

        class FakeNexus:
            def __init__(self, *_args, media_max_attempts: int) -> None:
                assert media_max_attempts == 1

            async def aclose(self) -> None:
                return None

            async def analyze_image(self, *, image_url: str, instruction: str) -> PromptToolProviderResult:
                nexus_calls.append((image_url, instruction))
                async with SessionFactory() as read_session:
                    stored = await read_session.get(PromptToolTask, task_id)
                    assert stored is not None
                    assert (stored.provider, stored.model) == ("nexus", "gpt-6-sol")
                    assert stored.input_payload["_prompt_tool_route_index"] == 1
                    assert stored.input_payload["_prompt_tool_nexus_started"]
                return PromptToolProviderResult(
                    model="gpt-6-sol",
                    payload={"prompt_ru": "Резервный промпт", "prompt_en": "Fallback prompt"},
                )

        monkeypatch.setattr("app.services.prompt_tool_execution.NexusPromptToolsClient", FakeNexus)
        claimed = await _claim(session, task_id)
        await PromptToolProcessor.process(session, AsyncMock(), claimed)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        assert stored is not None and stored.status == "succeeded"
        assert (stored.provider, stored.model) == ("nexus", "gpt-6-sol")
        assert len(probe.submitted) == len(nexus_calls) == 1
        await _assert_single_wallet_effect(session, user_id=user_id, task_id=task_id, cost=Decimal("1.00"))
        notifications = list(await session.scalars(select(Notification).where(Notification.user_id == user_id)))
        assert len(notifications) == 1 and notifications[0].body == "Резервный промпт"


@pytest.mark.asyncio
async def test_interrupted_managed_nexus_request_is_not_posted_again_after_reclaim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, admin):
        probe = _install_qwen_probe(monkeypatch)
        policy = await prompt_tool_routing.configured_prompt_tool_routes(session)
        policy["routes"]["image_analysis"] = [
            {"provider": "nexus", "model": "gpt-6-sol"},
            {"provider": "neironych", "model": "qwen3.8-max"},
        ]
        session.add(AdminRuntimeSetting(
            key=prompt_tool_routing.PROMPT_TOOL_ROUTES_SETTING_KEY,
            value={"revision": policy["revision"] + 1, "routes": policy["routes"]},
            updated_by_admin_id=admin.id,
        ))
        await session.commit()
        task, _key = await _create_media(session, user, "image_analysis")
        task_id, user_id = task.id, user.id
        nexus_calls = []

        class InterruptedNexus:
            def __init__(self, *_args, media_max_attempts: int) -> None:
                assert media_max_attempts == 1

            async def aclose(self) -> None:
                return None

            async def analyze_image(self, **kwargs) -> PromptToolProviderResult:
                nexus_calls.append(kwargs)
                async with SessionFactory() as read_session:
                    stored = await read_session.get(PromptToolTask, task_id)
                    assert stored is not None and stored.input_payload["_prompt_tool_nexus_started"]
                raise asyncio.CancelledError("Synthetic worker interruption after provider acceptance")

        monkeypatch.setattr("app.services.prompt_tool_execution.NexusPromptToolsClient", InterruptedNexus)
        interrupted = await _claim(session, task_id)
        with pytest.raises(asyncio.CancelledError):
            await PromptToolProcessor.process(session, AsyncMock(), interrupted)
        row = await session.get(PromptToolOutbox, interrupted.outbox_id, populate_existing=True)
        assert row is not None and row.status == "processing"
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        reclaimed = await _claim(session, task_id)
        assert reclaimed.attempts == interrupted.attempts + 1
        await PromptToolProcessor.process(session, AsyncMock(), reclaimed)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        assert stored is not None and stored.status == "failed" and stored.provider == "nexus"
        assert len(nexus_calls) == 1 and probe.submitted == []
        await _assert_single_wallet_effect(
            session, user_id=user_id, task_id=task_id, cost=Decimal("1.00"), refunded=True,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type", [ResourceLimitExceeded, ProtectionBackendUnavailable],
    ids=["resource-limit", "protection-backend-unavailable"],
)
async def test_protection_gate_defers_same_provider_without_post_refund_or_circuit_failure(
    monkeypatch: pytest.MonkeyPatch, error_type: type[Exception],
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, _admin):
        probe = _install_qwen_probe(monkeypatch)
        gate = AsyncMock(side_effect=[error_type("Synthetic protection delay", retry_after=37), None])
        failures, successes = AsyncMock(), AsyncMock()
        monkeypatch.setattr("app.services.prompt_tool_execution.AbuseProtectionService.provider_submission_gate", gate)
        monkeypatch.setattr("app.services.prompt_tool_execution.AbuseProtectionService.record_provider_failure", failures)
        monkeypatch.setattr("app.services.prompt_tool_execution.AbuseProtectionService.record_provider_success", successes)
        task, _key = await _create_media(session, user, "image_analysis")
        task_id, user_id = task.id, user.id
        claimed = await _claim(session, task_id)
        before = datetime.now(UTC)
        await PromptToolProcessor.process(session, AsyncMock(), claimed)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        row = await session.get(PromptToolOutbox, claimed.outbox_id, populate_existing=True)
        assert stored is not None and stored.status == "queued" and stored.provider == "neironych"
        assert stored.input_payload["_prompt_tool_route_index"] == 0
        assert "_qwen_submission" not in stored.input_payload
        assert row is not None and row.status == "pending"
        assert row.available_at >= before + timedelta(seconds=37)
        assert probe.prepared == [] and probe.submitted == [] and probe.nexus_calls == 0
        failures.assert_not_awaited()
        successes.assert_not_awaited()
        await _assert_single_wallet_effect(session, user_id=user_id, task_id=task_id, cost=Decimal("1.00"))

        row.available_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        reclaimed = await _claim(session, task_id)
        assert reclaimed.attempts == claimed.attempts + 1
        await PromptToolProcessor.process(session, AsyncMock(), reclaimed)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        assert stored is not None and stored.status == "succeeded" and stored.provider == "neironych"
        assert len(probe.submitted) == 1 and probe.nexus_calls == 0
        assert [call.args[1] for call in gate.await_args_list] == ["neironych-prompt-tools"] * 2
        failures.assert_not_awaited()
        successes.assert_awaited_once()
        await _assert_single_wallet_effect(session, user_id=user_id, task_id=task_id, cost=Decimal("1.00"))


@pytest.mark.asyncio
async def test_superseded_qwen_response_is_discarded_then_current_claim_recovers_saved_body(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    async with _funded_user(monkeypatch, isolate_queue=True) as (session, user, _admin):
        probe = _install_qwen_probe(monkeypatch)
        task, _key = await _create_media(session, user, "video_prompt")
        task_id, user_id = task.id, user.id
        original = await _claim(session, task_id)
        current_claims: list[ClaimedPromptTool] = []
        original_submit = probe.submit

        async def superseded_submit(**kwargs) -> PromptToolProviderResult:
            result = await original_submit(**kwargs)
            if not current_claims:
                async with SessionFactory() as other:
                    row = await other.get(PromptToolOutbox, original.outbox_id)
                    assert row is not None and row.status == "processing"
                    row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
                    await other.commit()
                    current = await _claim(other, task_id)
                    assert current.attempts == original.attempts + 1
                    current_claims.append(current)
            return result

        monkeypatch.setattr(probe, "submit", superseded_submit)
        with caplog.at_level(logging.INFO, logger="app.services.prompt_tool_execution"):
            async with asyncio.timeout(15):
                await PromptToolProcessor.process(session, AsyncMock(), original)
        messages = [
            record.getMessage() for record in caplog.records
            if record.name == "app.services.prompt_tool_execution" and f"task_id={task_id}" in record.getMessage()
        ]
        assert any("outcome=stale_claim" in message for message in messages)
        assert not any("outcome=succeeded" in message for message in messages)
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        row = await session.get(PromptToolOutbox, original.outbox_id, populate_existing=True)
        assert stored is not None and stored.status == "processing" and stored.result_payload == {}
        assert row is not None and row.status == "processing" and row.attempts == current_claims[0].attempts
        assert len(probe.prepared) == len(probe.submitted) == 1
        notifications = list(await session.scalars(select(Notification).where(Notification.user_id == user_id)))
        assert notifications == []
        await _assert_single_wallet_effect(session, user_id=user_id, task_id=task_id, cost=Decimal("30.00"))
        snapshot = dict(stored.input_payload["_qwen_submission"])

        probe.preparer_changed = True
        await PromptToolProcessor.process(session, AsyncMock(), current_claims[0])
        stored = await session.get(PromptToolTask, task_id, populate_existing=True)
        assert stored is not None and stored.status == "succeeded"
        assert stored.input_payload["_qwen_submission"] == snapshot
        assert len(probe.prepared) == 1 and len(probe.submitted) == 2
        assert probe.submitted[0] == probe.submitted[1] and probe.nexus_calls == 0
        notifications = list(await session.scalars(select(Notification).where(Notification.user_id == user_id)))
        assert len(notifications) == 1
        await _assert_single_wallet_effect(session, user_id=user_id, task_id=task_id, cost=Decimal("30.00"))
