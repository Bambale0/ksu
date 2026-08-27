from __future__ import annotations

import json
from typing import Any

import pytest

from app.providers.kie_prompt_tools import (
    KiePromptToolsClient,
    PromptToolProviderError,
)


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _Client:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.posts: list[dict[str, Any]] = []

    async def post(self, path: str, *, json: dict[str, Any]) -> _Response:
        assert path == "/codex/v1/responses"
        self.posts.append(json)
        return _Response(self.responses.pop(0))


def _responses_payload(text: str) -> dict[str, Any]:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
    }


@pytest.mark.asyncio
async def test_gpt55_prompt_builder_retries_invalid_json_without_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object.__new__(KiePromptToolsClient)
    client._client = _Client(
        [
            _responses_payload("не json"),
            _responses_payload(
                json.dumps(
                    {
                        "prompt_ru": "Русский production-ready prompt",
                        "prompt_en": "English production-ready prompt",
                    },
                    ensure_ascii=False,
                )
            ),
        ]
    )

    async def forbidden_gemini(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Gemini fallback must not run for text-only prompt builder")

    monkeypatch.setattr(KiePromptToolsClient, "_build_prompt_with_gemini", forbidden_gemini)

    result = await client.build_prompt(text="Сценарий для Seedance")

    assert result.model == "gpt-5-5"
    assert result.payload["prompt_ru"] == "Русский production-ready prompt"
    assert len(client._client.posts) == 2
    assert client._client.posts[0]["text"]["format"]["name"] == "prompt_pair"
    assert "Return valid JSON only" in client._client.posts[0]["input"][1]["content"][0]["text"]


@pytest.mark.asyncio
async def test_gpt55_prompt_builder_fails_closed_instead_of_gemini_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object.__new__(KiePromptToolsClient)
    client._client = _Client([_responses_payload(""), _responses_payload("still not json")])

    async def forbidden_gemini(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Gemini fallback must not run for text-only prompt builder")

    monkeypatch.setattr(KiePromptToolsClient, "_build_prompt_with_gemini", forbidden_gemini)

    with pytest.raises(PromptToolProviderError, match="GPT-5.5 prompt builder failed"):
        await client.build_prompt(text="Сценарий для Seedance")
