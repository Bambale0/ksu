from __future__ import annotations

from typing import Any

import httpx

from app.providers.kie_prompt_tools import (
    GPT_PROMPT_MAX_ATTEMPTS,
    PromptToolProviderError,
    PromptToolProviderResult,
    _PROMPT_SYSTEM,
    _gpt_prompt_builder_user_text,
    _parse_json_object,
    _prompt_pair,
)

GPT55_MODEL = "gpt-5.5"


def _chat_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Nexus GPT-5.5 returned no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("Nexus GPT-5.5 returned no assistant message")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text)
        if parts:
            return "\n".join(parts)
    raise ValueError("Nexus GPT-5.5 returned empty content")


class NexusPromptToolsClient:
    """Text-only GPT-5.5 adapter over Nexus OpenAI-compatible Chat Completions."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://nexusapi.dev",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key:
            raise PromptToolProviderError("NEXUS_API_KEY is not configured")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(base_url or "").rstrip("/"),
            timeout=httpx.Timeout(90.0, connect=10.0),
            headers={"Authorization": f"Bearer {clean_key}"},
        )
        self._authorization = f"Bearer {clean_key}"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def build_prompt(self, *, text: str) -> PromptToolProviderResult:
        user_text = _gpt_prompt_builder_user_text(text)
        body: dict[str, Any] = {
            "model": GPT55_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": _PROMPT_SYSTEM},
                {"role": "user", "content": user_text},
            ],
            "reasoning_effort": "medium",
            "max_completion_tokens": 2048,
        }

        last_error: Exception | None = None
        for attempt in range(GPT_PROMPT_MAX_ATTEMPTS):
            try:
                response = await self._client.post(
                    "/v1/chat/completions",
                    headers={"Authorization": self._authorization},
                    json=body,
                )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Nexus GPT-5.5 response must be an object")
                payload = _prompt_pair(_parse_json_object(_chat_content(data)))
                return PromptToolProviderResult(
                    model=GPT55_MODEL,
                    payload=payload,
                    credits_consumed=None,
                )
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                last_error = exc
                if attempt >= GPT_PROMPT_MAX_ATTEMPTS - 1:
                    break
                body = {
                    **body,
                    "messages": [
                        body["messages"][0],
                        {
                            "role": "user",
                            "content": (
                                f"{user_text}\n\n"
                                "Previous response was not valid for the required schema. "
                                "Return only a JSON object with string fields prompt_ru and prompt_en."
                            ),
                        },
                    ],
                }

        raise PromptToolProviderError(
            f"Nexus GPT-5.5 prompt builder failed: {last_error or 'unknown error'}"
        ) from last_error
