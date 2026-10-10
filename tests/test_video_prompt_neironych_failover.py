from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import settings
from app.providers.kie_prompt_tools import PromptToolProviderError, PromptToolProviderResult
from app.services.abuse_protection import ProviderCircuitOpen
from app.services.prompt_tools import (
    ClaimedPromptTool,
    PromptToolOutboxService,
    PromptToolProcessor,
    _prompt_tool_lease_seconds,
)


async def _exercise(
    monkeypatch: pytest.MonkeyPatch,
    *,
    gateway_status: int | None = 503,
    fallback_enabled: bool = True,
    circuit_open: bool = False,
    neironych_failed: bool = False,
    initial_provider: str = "nexus",
    persist_allowed: bool = True,
) -> dict[str, object]:
    task = SimpleNamespace(
        id=uuid.uuid4(),
        provider=initial_provider,
        tool="video_prompt",
        input_payload={
            "video_url": "https://app.example.test/uploads/refs/video/sample.mp4",
            "instruction": "cinematic",
            "duration_seconds": 10,
        },
    )
    events: dict[str, object] = {"nexus_calls": 0, "neironych_calls": 0}
    complete, release, refund = AsyncMock(), AsyncMock(), AsyncMock()
    persist = AsyncMock(return_value=persist_allowed)
    record_success, record_failure = AsyncMock(), AsyncMock()
    gate = AsyncMock()

    async def gated(_redis: object, name: str) -> None:
        if circuit_open and name == "nexus-prompt-tools":
            raise ProviderCircuitOpen("Circuit temporarily open", retry_after=55)

    gate.side_effect = gated

    class FakeSession:
        async def get(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            return task

        async def rollback(self) -> None:
            return None

    class FakeNexus:
        def __init__(self, *_args: object) -> None:
            pass

        async def aclose(self) -> None:
            return None

        async def build_video_prompt(
            self, *, video_url: str, instruction: str = "",
            duration_seconds: int | None = None,
        ) -> PromptToolProviderResult:
            events["nexus_calls"] = int(events["nexus_calls"]) + 1
            assert video_url.endswith("/sample.mp4")
            assert duration_seconds == 10
            request = httpx.Request("POST", "https://nexusapi.dev/v1/chat/completions")
            if gateway_status is None:
                raise PromptToolProviderError("Ambiguous Nexus timeout") from httpx.ReadTimeout(
                    "Nexus may have received the request", request=request
                )
            response = httpx.Response(gateway_status, request=request)
            error = httpx.HTTPStatusError(
                "Nexus gateway rejected the request", request=request, response=response,
            )
            raise PromptToolProviderError("Nexus video prompt failed") from error

    class FakeNeironych:
        def __init__(self, *_args: object) -> None:
            pass

        async def aclose(self) -> None:
            return None

        async def build_video_prompt(
            self, *, video_url: str, instruction: str = "",
            duration_seconds: int | None = None, idempotency_key: str,
        ) -> PromptToolProviderResult:
            events["neironych_calls"] = int(events["neironych_calls"]) + 1
            if initial_provider == "nexus":
                assert persist.await_count == 1, "Persist provider choice before any paid POST"
            assert video_url == "https://app.example.test/uploads/refs/video/sample.mp4"
            assert instruction == "cinematic" and duration_seconds == 10
            assert idempotency_key.endswith(str(task.id))
            if neironych_failed:
                raise PromptToolProviderError("Neironych is also unavailable")
            return PromptToolProviderResult(
                model="grok-4.5",
                payload={"prompt_ru": "Описание", "prompt_en": "Description"},
                credits_consumed=None,
            )

    class ForbiddenKie:
        def __init__(self, *_args: object) -> None:
            raise AssertionError("Kie must never serve Grok fallback")

    monkeypatch.setattr(settings, "prompt_tool_video_neironych_fallback_enabled", fallback_enabled, raising=False)
    monkeypatch.setattr(settings, "neironych_api_key", "synthetic-test-key")
    monkeypatch.setattr("app.services.prompt_tools.NexusPromptToolsClient", FakeNexus)
    monkeypatch.setattr("app.services.prompt_tools.NeironychVideoPromptClient", FakeNeironych)
    monkeypatch.setattr("app.services.prompt_tools.KiePromptToolsClient", ForbiddenKie)
    monkeypatch.setattr(
        "app.services.prompt_tools.AbuseProtectionService.provider_submission_gate", gate,
    )
    monkeypatch.setattr(
        "app.services.prompt_tools.AbuseProtectionService.record_provider_success",
        record_success,
    )
    monkeypatch.setattr(
        "app.services.prompt_tools.AbuseProtectionService.record_provider_failure",
        record_failure,
    )
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.route_to_provider", persist, raising=False)
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.complete", complete)
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.release", release)
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.fail_and_refund", refund)
    claimed = ClaimedPromptTool(outbox_id=uuid.uuid4(), task_id=task.id, attempts=1)
    redis = object()
    session = FakeSession()
    await PromptToolProcessor.process(session, redis, claimed)  # type: ignore[arg-type]
    events.update(
        {
            "session": session,
            "claimed": claimed,
            "persist": persist,
            "redis": redis,
            "gate": gate,
            "success": record_success,
            "failure": record_failure,
            "complete": complete,
            "release": release,
            "refund": refund,
        }
    )
    return events


@pytest.mark.asyncio
async def test_video_prompt_uses_neironych_on_explicit_nexus_503_without_second_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch)
    assert events["nexus_calls"] == 1
    assert events["neironych_calls"] == 1
    events["persist"].assert_awaited_once_with(
        events["session"], events["claimed"], provider="neironych", model="grok-4.5"
    )
    events["complete"].assert_awaited_once()
    assert events["complete"].await_args.kwargs["model"] == "grok-4.5"
    events["release"].assert_not_awaited()
    events["refund"].assert_not_awaited()
    events["failure"].assert_any_await(events["redis"], "nexus-prompt-tools")
    events["success"].assert_awaited_once_with(events["redis"], "neironych-prompt-tools")


@pytest.mark.asyncio
async def test_video_prompt_bypasses_open_nexus_circuit_for_neironych(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, circuit_open=True)
    assert events["nexus_calls"] == 0
    assert events["neironych_calls"] == 1
    events["complete"].assert_awaited_once()
    events["gate"].assert_any_await(events["redis"], "neironych-prompt-tools")
    events["success"].assert_awaited_once_with(events["redis"], "neironych-prompt-tools")


@pytest.mark.asyncio
async def test_video_prompt_never_falls_back_on_nexus_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, gateway_status=400)
    assert events["nexus_calls"] == 1
    assert events["neironych_calls"] == 0
    events["complete"].assert_not_awaited()
    events["release"].assert_awaited_once()


@pytest.mark.asyncio
async def test_video_prompt_fallback_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, fallback_enabled=False)
    assert events["neironych_calls"] == 0
    events["release"].assert_awaited_once()
    events["complete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_video_prompt_does_not_complete_when_both_providers_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, neironych_failed=True)
    assert events["nexus_calls"] == 1 and events["neironych_calls"] == 1
    events["complete"].assert_not_awaited()
    events["release"].assert_awaited_once()
    events["failure"].assert_any_await(events["redis"], "nexus-prompt-tools")
    events["failure"].assert_any_await(events["redis"], "neironych-prompt-tools")

@pytest.mark.asyncio
async def test_video_prompt_never_cross_submits_after_ambiguous_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, gateway_status=None)
    assert events["nexus_calls"] == 1
    assert events["neironych_calls"] == 0
    events["release"].assert_awaited_once()
    events["complete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_fallback_persists_actual_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = SimpleNamespace(
        tool="prompt_builder",
        status="processing",
        provider="nexus",
        model="gpt-6-sol",
    )
    outbox = SimpleNamespace(status="processing")
    claimed = ClaimedPromptTool(outbox_id=uuid.uuid4(), task_id=uuid.uuid4(), attempts=1)

    class FakeSession:
        commit = AsyncMock()

    monkeypatch.setattr(
        PromptToolOutboxService,
        "_lock_current_claim",
        AsyncMock(return_value=(task, outbox)),
    )
    session = FakeSession()
    await PromptToolOutboxService.complete(
        session,  # type: ignore[arg-type]
        claimed,
        result={"prompt_ru": "OK", "prompt_en": "OK"},
        model="grok-4.5",
        provider_credits=Decimal("1.25"),
        provider="neironych",
    )
    assert task.provider == "neironych"
    assert task.model == "grok-4.5"
    assert task.status == "succeeded" and outbox.status == "completed"
    assert task.provider_credits == Decimal("1.25")
    session.commit.assert_awaited_once()



def test_video_prompt_lease_is_longer_than_general_generation_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "generation_outbox_lease_seconds", 90)
    monkeypatch.setattr(settings, "prompt_tool_video_outbox_lease_seconds", 600)
    assert _prompt_tool_lease_seconds("video_prompt") == 600
    assert _prompt_tool_lease_seconds("image_analysis") == 90
    assert _prompt_tool_lease_seconds("prompt_builder") == 90

@pytest.mark.asyncio
async def test_grok45_is_pinned_after_a_failed_provider_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, initial_provider="neironych")
    assert events["nexus_calls"] == 0
    assert events["neironych_calls"] == 1
    events["persist"].assert_not_awaited()
    events["complete"].assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_lease_cannot_submit_paid_grok_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, persist_allowed=False)
    assert events["nexus_calls"] == 1
    assert events["persist"].await_count == 1
    assert events["neironych_calls"] == 0
    events["complete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_switch_to_neironych_persists_route_before_provider_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = SimpleNamespace(
        status="processing", provider="nexus", model="gpt-6-sol",
        tool="video_prompt",
    )
    row = SimpleNamespace(status="processing")
    claimed = ClaimedPromptTool(
        outbox_id=uuid.uuid4(), task_id=uuid.uuid4(), attempts=1
    )
    class FakeSession:
        commit = AsyncMock()
        rollback = AsyncMock()
    session = FakeSession()
    monkeypatch.setattr(
        PromptToolOutboxService, "_lock_current_claim",
        AsyncMock(return_value=(task, row)),
    )
    result = await PromptToolOutboxService.route_to_provider(
        session, claimed, provider="neironych", model="grok-4.5"
    )
    assert result is True
    assert task.provider == "neironych" and task.model == "grok-4.5"
    session.commit.assert_awaited_once()
