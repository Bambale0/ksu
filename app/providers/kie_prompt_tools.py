from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx


class PromptToolProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PromptToolProviderResult:
    model: str
    payload: dict[str, Any]
    credits_consumed: Decimal | None = None


_IMAGE_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "image_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "composition": {"type": "string"},
                "subjects": {"type": "array", "items": {"type": "string"}},
                "style": {"type": "string"},
                "lighting": {"type": "string"},
                "colors": {"type": "array", "items": {"type": "string"}},
                "camera": {"type": "string"},
                "details": {"type": "array", "items": {"type": "string"}},
                "generation_notes": {"type": "string"},
            },
            "required": [
                "summary",
                "composition",
                "subjects",
                "style",
                "lighting",
                "colors",
                "camera",
                "details",
                "generation_notes",
            ],
            "additionalProperties": False,
        },
    },
}

_PROMPT_PAIR_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "prompt_pair",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "prompt_ru": {"type": "string"},
                "prompt_en": {"type": "string"},
            },
            "required": ["prompt_ru", "prompt_en"],
            "additionalProperties": False,
        },
    },
}

_PROMPT_SYSTEM = (
    "Ты профессиональный prompt engineer для генерации изображений и видео. "
    "Пользователь может передать текст, изображение и/или аудиосообщение. "
    "Сохрани творческий замысел, композицию, свет, палитру, стиль, позу, окружение и ограничения, "
    "которые явно присутствуют во входах. Для изображения описывай только наблюдаемые свойства; "
    "не идентифицируй реальных людей и не угадывай чувствительные характеристики. "
    "Для аудио используй произнесённую идею как творческое направление, но не возвращай транскрипт. "
    "Создай ровно два цельных production-ready промпта с одинаковым смыслом: prompt_ru на русском "
    "и prompt_en на английском. Не добавляй negative prompt, рекомендации моделей, комментарии или markdown."
)


class KiePromptToolsClient:
    def __init__(self, api_key: str, base_url: str = "https://api.kie.ai") -> None:
        if not api_key:
            raise PromptToolProviderError("KIE_API_KEY is not configured")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(90.0, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def analyze_image(
        self,
        *,
        image_url: str,
        instruction: str = "",
    ) -> PromptToolProviderResult:
        system = (
            "Ты визуальный аналитик для подготовки AI-генераций. Опиши только наблюдаемые "
            "визуальные свойства изображения: композицию, объекты, стиль, свет, цвета, ракурс, "
            "материалы и важные детали. Не пытайся идентифицировать реальных людей и не делай "
            "выводов о чувствительных личных характеристиках. Отвечай по-русски в заданной JSON-схеме."
        )
        user_text = "Подробно проанализируй изображение для последующего создания промпта."
        if instruction.strip():
            user_text += f" Пользовательский фокус: {instruction.strip()}"
        body = {
            "model": "gemini-2.5-pro",
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "response_format": _IMAGE_ANALYSIS_SCHEMA,
        }
        try:
            response = await self._client.post("/gemini-2.5-pro/v1/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
            payload = _parse_json_object(content)
            return PromptToolProviderResult(
                model="gemini-2.5-pro",
                payload=payload,
                credits_consumed=_credits(data),
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise PromptToolProviderError(f"Image analysis provider failed: {exc}") from exc

    async def build_prompt(
        self,
        *,
        text: str,
        image_url: str | None = None,
        audio_url: str | None = None,
    ) -> PromptToolProviderResult:
        # Kie documents GPT-5.5 Responses for text/image/file inputs, but does
        # not document input_audio on that endpoint. Gemini 2.5 Pro explicitly
        # accepts audio URLs through the same multimodal image_url content type.
        # Use Gemini for audio and as a documented text/image fallback.
        if audio_url:
            return await self._build_prompt_with_gemini(
                text=text,
                image_url=image_url,
                audio_url=audio_url,
            )
        try:
            return await self._build_prompt_with_gpt55(text=text, image_url=image_url)
        except PromptToolProviderError as primary_exc:
            try:
                return await self._build_prompt_with_gemini(
                    text=text,
                    image_url=image_url,
                    audio_url=None,
                )
            except PromptToolProviderError as fallback_exc:
                raise PromptToolProviderError(
                    f"Prompt builder providers failed: primary={primary_exc}; fallback={fallback_exc}"
                ) from fallback_exc

    async def _build_prompt_with_gpt55(
        self,
        *,
        text: str,
        image_url: str | None,
    ) -> PromptToolProviderResult:
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": text.strip() or "Создай подробный промпт по изображению.",
            }
        ]
        if image_url:
            content.append({"type": "input_image", "image_url": image_url})
        body = {
            "model": "gpt-5-5",
            "stream": False,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": _PROMPT_SYSTEM}]},
                {"role": "user", "content": content},
            ],
            "reasoning": {"effort": "medium"},
        }
        try:
            response = await self._client.post("/codex/v1/responses", json=body)
            response.raise_for_status()
            data = response.json()
            payload = _prompt_pair(_parse_json_object(_responses_output_text(data)))
            return PromptToolProviderResult(
                model="gpt-5-5",
                payload=payload,
                credits_consumed=_credits(data),
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise PromptToolProviderError(f"GPT-5.5 prompt builder failed: {exc}") from exc

    async def _build_prompt_with_gemini(
        self,
        *,
        text: str,
        image_url: str | None,
        audio_url: str | None,
    ) -> PromptToolProviderResult:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": text.strip()
                or (
                    "Создай подробный промпт на основе переданного визуального или голосового "
                    "референса."
                ),
            }
        ]
        for media_url in (image_url, audio_url):
            if media_url:
                content.append({"type": "image_url", "image_url": {"url": media_url}})
        body = {
            "model": "gemini-2.5-pro",
            "stream": False,
            "messages": [
                {"role": "system", "content": _PROMPT_SYSTEM},
                {"role": "user", "content": content},
            ],
            "response_format": _PROMPT_PAIR_SCHEMA,
        }
        try:
            response = await self._client.post("/gemini-2.5-pro/v1/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            content_text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
            payload = _prompt_pair(_parse_json_object(content_text))
            return PromptToolProviderResult(
                model="gemini-2.5-pro",
                payload=payload,
                credits_consumed=_credits(data),
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise PromptToolProviderError(f"Gemini prompt builder failed: {exc}") from exc


def _responses_output_text(data: dict[str, Any]) -> str:
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text" and part.get("text"):
                return str(part["text"])
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return str(data["output_text"])
    raise ValueError("Provider returned no output_text")


def _prompt_pair(payload: dict[str, Any]) -> dict[str, str]:
    prompt_ru = str(payload.get("prompt_ru") or "").strip()
    prompt_en = str(payload.get("prompt_en") or "").strip()
    if not prompt_ru or not prompt_en:
        raise ValueError("Provider returned incomplete prompt pair")
    return {"prompt_ru": prompt_ru, "prompt_en": prompt_en}


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return parsed


def _credits(data: dict[str, Any]) -> Decimal | None:
    raw = data.get("credits_consumed")
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except (ValueError, TypeError):
        return None
