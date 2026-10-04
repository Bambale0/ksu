from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.providers.kie_prompt_tools import PromptToolProviderResult
from app.providers.nexus_prompt_tools import NexusPromptToolsClient
from app.services.prompt_tools import (
    ClaimedPromptTool,
    PromptToolProcessor,
    _provider_for_prompt_tool,
)


@pytest.mark.asyncio
async def test_nexus_gpt55_prompt_builder_uses_openai_chat_completions_and_retries_json() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        calls.append(body)
        content = (
            "not-json"
            if len(calls) == 1
            else json.dumps(
                {
                    "prompt_ru": "Русский production-ready prompt",
                    "prompt_en": "English production-ready prompt",
                },
                ensure_ascii=False,
            )
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": content}}]},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusPromptToolsClient("test-key", client=http_client)
        result = await client.build_prompt(text="Сценарий для Seedance")

    assert result.model == "gpt-5.5"
    assert result.payload["prompt_ru"] == "Русский production-ready prompt"
    assert len(calls) == 2
    assert calls[0]["model"] == "gpt-5.5"
    assert calls[0]["stream"] is False
    assert calls[0]["reasoning_effort"] == "medium"
    assert "Return valid JSON only" in calls[0]["messages"][1]["content"]
    assert "Previous response was not valid" in calls[1]["messages"][1]["content"]


def test_prompt_tool_provider_routes_new_tasks_to_nexus() -> None:
    assert _provider_for_prompt_tool(
        "prompt_builder", {"text": "portrait", "image_url": None}
    ) == "nexus"
    assert _provider_for_prompt_tool(
        "prompt_builder", {"text": "match image", "image_url": "https://example.test/ref.jpg"}
    ) == "nexus"
    assert _provider_for_prompt_tool("video_prompt", {"video_url": "https://example.test/ref.mp4"}) == "nexus"
    assert _provider_for_prompt_tool("image_analysis", {"image_url": "https://example.test/ref.jpg"}) == "nexus"


@pytest.mark.asyncio
async def test_prompt_processor_dispatches_persisted_nexus_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = SimpleNamespace(
        provider="nexus",
        tool="prompt_builder",
        input_payload={"text": "portrait", "image_url": None},
    )

    class FakeSession:
        async def get(self, *_args, **_kwargs):
            return task

        async def rollback(self) -> None:
            raise AssertionError("rollback is not expected")

    class FakeNexus:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        async def aclose(self) -> None:
            return None

        async def build_prompt(self, *, text: str, image_url: str | None = None) -> PromptToolProviderResult:
            assert text == "portrait"
            assert image_url is None
            return PromptToolProviderResult(
                model="gpt-5.5",
                payload={"prompt_ru": "RU", "prompt_en": "EN"},
            )

    class ForbiddenKie:
        def __init__(self, *_args, **_kwargs) -> None:
            raise AssertionError("Kie must not be constructed for a persisted Nexus task")

    complete = AsyncMock()
    gate = AsyncMock()
    success = AsyncMock()
    failure = AsyncMock()

    monkeypatch.setattr("app.services.prompt_tools.NexusPromptToolsClient", FakeNexus)
    monkeypatch.setattr("app.services.prompt_tools.KiePromptToolsClient", ForbiddenKie)
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.complete", complete)
    monkeypatch.setattr("app.services.prompt_tools.AbuseProtectionService.provider_submission_gate", gate)
    monkeypatch.setattr("app.services.prompt_tools.AbuseProtectionService.record_provider_success", success)
    monkeypatch.setattr("app.services.prompt_tools.AbuseProtectionService.record_provider_failure", failure)

    claimed = ClaimedPromptTool(outbox_id=uuid.uuid4(), task_id=uuid.uuid4(), attempts=1)
    redis = object()
    await PromptToolProcessor.process(
        FakeSession(),  # type: ignore[arg-type]
        redis,  # type: ignore[arg-type]
        claimed,
    )

    gate.assert_awaited_once_with(redis, "nexus-prompt-tools")
    complete.assert_awaited_once()
    assert complete.await_args.kwargs["model"] == "gpt-5.5"
    success.assert_awaited_once_with(redis, "nexus-prompt-tools")
    failure.assert_not_awaited()
