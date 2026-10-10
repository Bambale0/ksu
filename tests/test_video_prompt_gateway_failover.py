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
)


async def _exercise(
    monkeypatch: pytest.MonkeyPatch,
    *,
    gateway_status: int | None = 503,
    fallback_enabled: bool = True,
    circuit_open: bool = False,
    kie_failed: bool = False,
) -> dict[str, object]:
    task = SimpleNamespace(
        id=uuid.uuid4(),
        provider="nexus",
        tool="video_prompt",
        input_payload={
            "video_url": "https://app.example.test/uploads/refs/video/sample.mp4",
            "instruction": "cinematic",
            "duration_seconds": 10,
        },
    )
    events: dict[str, object] = {"nexus_calls": 0, "kie_calls": 0}
    complete, release, refund = AsyncMock(), AsyncMock(), AsyncMock()
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

    class FakeKie:
        def __init__(self, *_args: object) -> None:
            pass

        async def aclose(self) -> None:
            return None

        async def build_video_prompt(
            self, *, video_url: str, instruction: str = "",
            duration_seconds: int | None = None,
        ) -> PromptToolProviderResult:
            events["kie_calls"] = int(events["kie_calls"]) + 1
            assert video_url == "https://transport.example.test/video.mp4"
            assert instruction == "cinematic" and duration_seconds == 10
            if kie_failed:
                raise PromptToolProviderError("Kie is also unavailable")
            return PromptToolProviderResult(
                model="gpt-5-5-frames",
                payload={"prompt_ru": "Описание", "prompt_en": "Description"},
                credits_consumed=Decimal("2.50"),
            )

    monkeypatch.setattr(settings, "prompt_tool_video_kie_fallback_enabled", fallback_enabled, raising=False)
    monkeypatch.setattr(settings, "kie_api_key", "synthetic-test-key")
    monkeypatch.setattr("app.services.prompt_tools.NexusPromptToolsClient", FakeNexus)
    monkeypatch.setattr("app.services.prompt_tools.KiePromptToolsClient", FakeKie)
    monkeypatch.setattr(
        "app.services.provider_media_transport.ProviderMediaTransport.prepare",
        AsyncMock(return_value={"video_url": "https://transport.example.test/video.mp4"}),
    )
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
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.complete", complete)
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.release", release)
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.fail_and_refund", refund)
    claimed = ClaimedPromptTool(outbox_id=uuid.uuid4(), task_id=task.id, attempts=1)
    redis = object()
    await PromptToolProcessor.process(FakeSession(), redis, claimed)  # type: ignore[arg-type]
    events.update(
        {
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
async def test_video_prompt_uses_kie_on_explicit_nexus_503_without_second_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch)
    assert events["nexus_calls"] == 1
    assert events["kie_calls"] == 1
    events["complete"].assert_awaited_once()
    assert events["complete"].await_args.kwargs["model"] == "gpt-5-5-frames"
    events["release"].assert_not_awaited()
    events["refund"].assert_not_awaited()
    events["failure"].assert_any_await(events["redis"], "nexus-prompt-tools")
    events["success"].assert_awaited_once_with(events["redis"], "kie-prompt-tools")


@pytest.mark.asyncio
async def test_video_prompt_bypasses_open_nexus_circuit_for_kie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, circuit_open=True)
    assert events["nexus_calls"] == 0
    assert events["kie_calls"] == 1
    events["complete"].assert_awaited_once()
    events["gate"].assert_any_await(events["redis"], "kie-prompt-tools")
    events["success"].assert_awaited_once_with(events["redis"], "kie-prompt-tools")


@pytest.mark.asyncio
async def test_video_prompt_never_falls_back_on_nexus_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, gateway_status=400)
    assert events["nexus_calls"] == 1
    assert events["kie_calls"] == 0
    events["complete"].assert_not_awaited()
    events["release"].assert_awaited_once()


@pytest.mark.asyncio
async def test_video_prompt_fallback_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, fallback_enabled=False)
    assert events["kie_calls"] == 0
    events["release"].assert_awaited_once()
    events["complete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_video_prompt_does_not_complete_when_both_providers_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, kie_failed=True)
    assert events["nexus_calls"] == 1 and events["kie_calls"] == 1
    events["complete"].assert_not_awaited()
    events["release"].assert_awaited_once()
    events["failure"].assert_any_await(events["redis"], "nexus-prompt-tools")
    events["failure"].assert_any_await(events["redis"], "kie-prompt-tools")

@pytest.mark.asyncio
async def test_video_prompt_never_cross_submits_after_ambiguous_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, gateway_status=None)
    assert events["nexus_calls"] == 1
    assert events["kie_calls"] == 0
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
        model="gpt-5-5-frames",
        provider_credits=Decimal("1.25"),
        provider="kie",
    )
    assert task.provider == "kie"
    assert task.model == "gpt-5-5-frames"
    assert task.status == "succeeded" and outbox.status == "completed"
    assert task.provider_credits == Decimal("1.25")
    session.commit.assert_awaited_once()
