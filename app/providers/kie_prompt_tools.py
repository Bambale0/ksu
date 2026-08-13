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
    ) -> PromptToolProviderResult:
        system = (
            "Ты профессиональный prompt engineer для генерации изображений и видео. "
            "На основе текста пользователя и, если передано, изображения создай два цельных подробных "
            "промпта с одинаковым смыслом: на русском и английском. Не идентифицируй реальных людей "
            "по изображению и не угадывай чувствительные характеристики. Верни только JSON-объект "
            'вида {"prompt_ru":"...","prompt_en":"..."} без markdown.'
        )
        content: list[dict[str, Any]] = [
            {"type": "input_text", "text": text.strip() or "Создай подробный промпт по изображению."}
        ]
        if image_url:
            content.append({"type": "input_image", "image_url": image_url})
        body = {
            "model": "gpt-5-5",
            "stream": False,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {"role": "user", "content": content},
            ],
            "reasoning": {"effort": "medium"},
        }
        try:
            response = await self._client.post("/codex/v1/responses", json=body)
            response.raise_for_status()
            data = response.json()
            text_output = _responses_output_text(data)
            payload = _parse_json_object(text_output)
            prompt_ru = str(payload.get("prompt_ru") or "").strip()
            prompt_en = str(payload.get("prompt_en") or "").strip()
            if not prompt_ru or not prompt_en:
                raise ValueError("Provider returned incomplete prompt pair")
            return PromptToolProviderResult(
                model="gpt-5-5",
                payload={"prompt_ru": prompt_ru, "prompt_en": prompt_en},
                credits_consumed=_credits(data),
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise PromptToolProviderError(f"Prompt builder provider failed: {exc}") from exc


def _responses_output_text(data: dict[str, Any]) -> str:
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text" and part.get("text"):
                return str(part["text"])
    raise ValueError("Provider returned no output_text")


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
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
