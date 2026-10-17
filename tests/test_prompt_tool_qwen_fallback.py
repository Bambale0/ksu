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
    qwen_failed: bool = False,
    qwen_http_status: int | None = None,
    initial_provider: str = "nexus",
    persist_allowed: bool = True,
    tool: str = "video_prompt",
) -> dict[str, object]:
    task = SimpleNamespace(
        id=uuid.uuid4(),
        provider=initial_provider,
        tool=tool,
        input_payload=(
            {"image_url": "https://app.example.test/uploads/refs/photo/sample.jpg",
             "instruction": "cinematic"}
            if tool == "image_analysis"
            else {"video_url": "https://app.example.test/uploads/refs/video/sample.mp4",
                  "instruction": "cinematic", "duration_seconds": 10}
        ),
    )
    events: dict[str, object] = {"nexus_calls": 0, "qwen_calls": 0}
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

    def _gateway_error() -> PromptToolProviderError:
        request = httpx.Request("POST", "https://nexusapi.dev/v1/chat/completions")
        try:
            if gateway_status is None:
                raise httpx.ReadTimeout("Ambiguous timeout", request=request)
            response = httpx.Response(gateway_status, request=request)
            raise httpx.HTTPStatusError("Nexus gateway rejected", request=request, response=response)
        except httpx.HTTPError as cause:
            error = PromptToolProviderError("Nexus prompt failed")
            error.__cause__ = cause
            return error

    class FakeNexus:
        def __init__(self, *_args: object) -> None:
            pass

        async def aclose(self) -> None:
            return None

        async def analyze_image(
            self, *, image_url: str, instruction: str = ""
        ) -> PromptToolProviderResult:
            events["nexus_calls"] = int(events["nexus_calls"]) + 1
            assert image_url.endswith("/sample.jpg")
            assert instruction == "cinematic"
            if gateway_status == 200:
                return PromptToolProviderResult(
                    model="gpt-6-sol", payload={"prompt_ru": "Основной",
                      "prompt_en": "Primary"}, credits_consumed=None
                )
            raise _gateway_error()

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
            if gateway_status == 200:
                return PromptToolProviderResult(
                    model="gpt-6-sol", payload={"prompt_ru": "Основной",
                    "prompt_en": "Primary"}, credits_consumed=None,
                )
            raise _gateway_error()

    class FakeQwen:
        def __init__(self, *_args: object) -> None:
            pass

        async def aclose(self) -> None:
            return None

        async def analyze_image(
            self, *, image_url: str, instruction: str = "",
            idempotency_key: str,
        ) -> PromptToolProviderResult:
            events["qwen_calls"] = int(events["qwen_calls"]) + 1
            assert image_url.endswith("/sample.jpg")
            assert instruction == "cinematic"
            assert idempotency_key == str(task.id)
            if qwen_failed:
                raise PromptToolProviderError("Neironych Qwen unavailable")
            if qwen_http_status is not None:
                req = httpx.Request("POST", "https://api.xn--e1aikcel5c5a.online/v1/chat/completions")
                res = httpx.Response(qwen_http_status, request=req)
                try:
                    raise httpx.HTTPStatusError("Qwen rejected request", request=req, response=res)
                except httpx.HTTPStatusError as cause:
                    raise PromptToolProviderError("Qwen request failed") from cause
            return PromptToolProviderResult(
                model="qwen3.8-max",
                payload={"prompt_ru":"Запасной","prompt_en":"Backup"},
                credits_consumed=None,
            )

        async def build_video_prompt(
            self, *, video_url: str, instruction: str = "",
            duration_seconds: int | None = None, idempotency_key: str,
        ) -> PromptToolProviderResult:
            events["qwen_calls"] = int(events["qwen_calls"]) + 1
            if initial_provider == "nexus":
                assert persist.await_count == 1, "Persist provider choice before any paid POST"
            assert video_url == "https://app.example.test/uploads/refs/video/sample.mp4"
            assert instruction == "cinematic" and duration_seconds == 10
            assert idempotency_key.endswith(str(task.id))
            if qwen_failed:
                raise PromptToolProviderError("Neironych is also unavailable")
            return PromptToolProviderResult(
                model="qwen3.8-max",
                payload={"prompt_ru": "Описание", "prompt_en": "Description"},
                credits_consumed=None,
            )

    class ForbiddenKie:
        def __init__(self, *_args: object) -> None:
            raise AssertionError("Kie must never serve Qwen fallback")

    monkeypatch.setattr(settings, "prompt_tool_qwen_fallback_enabled", fallback_enabled, raising=False)
    monkeypatch.setattr(settings, "neironych_api_key", "synthetic-test-key")
    monkeypatch.setattr("app.services.prompt_tools.NexusPromptToolsClient", FakeNexus)
    monkeypatch.setattr("app.services.prompt_tools.NeironychQwenPromptToolsClient", FakeQwen)
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
async def test_video_prompt_uses_qwen_on_explicit_nexus_503_without_second_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch)
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 1
    events["persist"].assert_awaited_once_with(
        events["session"], events["claimed"], provider="neironych", model="qwen3.8-max"
    )
    events["complete"].assert_awaited_once()
    assert events["complete"].await_args.kwargs["model"] == "qwen3.8-max"
    events["release"].assert_not_awaited()
    events["refund"].assert_not_awaited()
    events["failure"].assert_any_await(events["redis"], "nexus-prompt-tools")
    events["success"].assert_awaited_once_with(events["redis"], "neironych-prompt-tools")


@pytest.mark.asyncio
async def test_video_prompt_bypasses_open_nexus_circuit_for_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, circuit_open=True)
    assert events["nexus_calls"] == 0
    assert events["qwen_calls"] == 1
    events["complete"].assert_awaited_once()
    events["gate"].assert_any_await(events["redis"], "neironych-prompt-tools")
    events["success"].assert_awaited_once_with(events["redis"], "neironych-prompt-tools")


@pytest.mark.asyncio
async def test_video_prompt_never_falls_back_on_nexus_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, gateway_status=400)
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 0
    events["complete"].assert_not_awaited()
    events["release"].assert_awaited_once()


@pytest.mark.asyncio
async def test_video_prompt_fallback_is_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, fallback_enabled=False)
    assert events["qwen_calls"] == 0
    events["release"].assert_awaited_once()
    events["complete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_video_prompt_does_not_complete_when_both_providers_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, qwen_failed=True)
    assert events["nexus_calls"] == 1 and events["qwen_calls"] == 1
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
    assert events["qwen_calls"] == 0
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
        model="qwen3.8-max",
        provider_credits=Decimal("1.25"),
        provider="neironych",
    )
    assert task.provider == "neironych"
    assert task.model == "qwen3.8-max"
    assert task.status == "succeeded" and outbox.status == "completed"
    assert task.provider_credits == Decimal("1.25")
    session.commit.assert_awaited_once()



def test_video_prompt_lease_is_longer_than_general_generation_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "generation_outbox_lease_seconds", 90)
    monkeypatch.setattr(settings, "prompt_tool_video_outbox_lease_seconds", 600)
    monkeypatch.setattr(settings, "prompt_tool_image_outbox_lease_seconds", 600)
    monkeypatch.setattr(settings, "prompt_tool_qwen_fallback_enabled", True)
    assert _prompt_tool_lease_seconds("video_prompt") == 600
    assert _prompt_tool_lease_seconds("image_analysis") == 600
    assert _prompt_tool_lease_seconds("prompt_builder") == 90
    monkeypatch.setattr(settings, "prompt_tool_qwen_fallback_enabled", False)
    assert _prompt_tool_lease_seconds("image_analysis") == 90
    assert _prompt_tool_lease_seconds("image_analysis", provider="neironych") == 600

@pytest.mark.asyncio
async def test_qwen38_is_pinned_after_a_failed_provider_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, initial_provider="neironych")
    assert events["nexus_calls"] == 0
    assert events["qwen_calls"] == 1
    events["persist"].assert_not_awaited()
    events["complete"].assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_lease_cannot_submit_paid_qwen_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, persist_allowed=False)
    assert events["nexus_calls"] == 1
    assert events["persist"].await_count == 1
    assert events["qwen_calls"] == 0
    events["complete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_switch_to_qwen_persists_route_before_provider_request(
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
        session, claimed, provider="neironych", model="qwen3.8-max"
    )
    assert result is True
    assert task.provider == "neironych" and task.model == "qwen3.8-max"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_photo_prompt_nexus_503_falls_back_to_qwen_without_second_rox_charge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, tool="image_analysis", gateway_status=503)
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 1
    events["persist"].assert_awaited_once_with(
        events["session"], events["claimed"], provider="neironych", model="qwen3.8-max"
    )
    events["complete"].assert_awaited_once()
    assert events["complete"].await_args.kwargs["model"] == "qwen3.8-max"
    events["refund"].assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_prompt_healthy_nexus_stays_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, tool="image_analysis", gateway_status=200)
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 0
    events["persist"].assert_not_awaited()
    events["complete"].assert_awaited_once()
    assert events["complete"].await_args.kwargs["provider"] == "nexus"


@pytest.mark.asyncio
async def test_photo_prompt_circuit_open_falls_back_to_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, tool="image_analysis", circuit_open=True)
    assert events["nexus_calls"] == 0
    assert events["qwen_calls"] == 1
    events["complete"].assert_awaited_once()


@pytest.mark.asyncio
async def test_photo_prompt_nexus_400_never_invokes_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, tool="image_analysis", gateway_status=400)
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 0
    events["complete"].assert_not_awaited()
    events["release"].assert_awaited_once()


@pytest.mark.asyncio
async def test_photo_prompt_ambiguous_timeout_never_cross_submits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, tool="image_analysis", gateway_status=None)
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 0
    events["complete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_prompt_already_pinned_to_qwen_never_returns_to_nexus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(
        monkeypatch, tool="image_analysis", initial_provider="neironych",
    )
    assert events["nexus_calls"] == 0
    assert events["qwen_calls"] == 1
    events["persist"].assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_fallback_cannot_submit_on_stale_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(
        monkeypatch, tool="image_analysis", persist_allowed=False,
    )
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 0
    events["complete"].assert_not_awaited()



@pytest.mark.asyncio
async def test_qwen_balance_402_refunds_without_pointless_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, tool="image_analysis", qwen_http_status=402)
    assert events["qwen_calls"] == 1
    events["complete"].assert_not_awaited()
    events["release"].assert_not_awaited()
    events["refund"].assert_awaited_once()



@pytest.mark.asyncio
async def test_video_prompt_healthy_nexus_never_calls_qwen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(monkeypatch, tool="video_prompt", gateway_status=200)
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 0
    events["persist"].assert_not_awaited()
    events["complete"].assert_awaited_once()
    assert events["complete"].await_args.kwargs["provider"] == "nexus"


@pytest.mark.asyncio
async def test_photo_prompt_fallback_requires_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = await _exercise(
        monkeypatch, tool="image_analysis", fallback_enabled=False,
    )
    assert events["nexus_calls"] == 1
    assert events["qwen_calls"] == 0
    events["release"].assert_awaited_once()
    events["complete"].assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_builder_never_uses_qwen_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = SimpleNamespace(
        id=uuid.uuid4(), provider="nexus", tool="prompt_builder",
        input_payload={"text":"A mountain landscape", "image_url":None},
    )
    calls = {"nexus":0,"qwen":0}
    class Session:
        async def get(self, *_args: object) -> SimpleNamespace:
            return task
        async def rollback(self) -> None:
            return None
    class FakeNexus:
        def __init__(self,*_args: object) -> None:
            pass
        async def aclose(self) -> None:
            return None
        async def build_prompt(self, *, text: str, image_url: str | None=None) -> PromptToolProviderResult:
            calls["nexus"] += 1
            return PromptToolProviderResult(
                model="gpt-5.5", payload={"prompt_ru":"описание","prompt_en":"description"},
                credits_consumed=None,
            )
    class FakeQwen:
        def __init__(self,*_args: object) -> None:
            calls["qwen"] += 1
    completed = AsyncMock()
    monkeypatch.setattr(settings,"prompt_tool_qwen_fallback_enabled",True)
    monkeypatch.setattr(settings,"neironych_api_key","synthetic-test-key")
    monkeypatch.setattr("app.services.prompt_tools.NexusPromptToolsClient",FakeNexus)
    monkeypatch.setattr("app.services.prompt_tools.NeironychQwenPromptToolsClient",FakeQwen)
    monkeypatch.setattr("app.services.prompt_tools.AbuseProtectionService.provider_submission_gate",AsyncMock())
    monkeypatch.setattr("app.services.prompt_tools.AbuseProtectionService.record_provider_success",AsyncMock())
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.complete",completed)
    claimed = ClaimedPromptTool(outbox_id=uuid.uuid4(),task_id=task.id,attempts=1)
    await PromptToolProcessor.process(Session(),object(),claimed)  # type: ignore[arg-type]
    assert calls == {"nexus":1,"qwen":0}
    assert completed.await_args.kwargs["provider"] == "nexus"
