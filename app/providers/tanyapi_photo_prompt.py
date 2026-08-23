from __future__ import annotations

import asyncio
import json
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.providers.kie_prompt_tools import PromptToolProviderError, PromptToolProviderResult

PRIMARY_MODEL = "gpt-5-4"
FALLBACK_MODEL = "gpt-5-2"
CLAUDE_MODEL = "claude-haiku-4-5"
GPT_MAX_ATTEMPTS = 3
CLAUDE_MAX_ATTEMPTS = 2

SYSTEM_PROMPT = """
You are a senior prompt analyst for photorealistic AI image generation.

Your task:
Analyze the attached reference image and create a polished generation prompt.

Primary output style:
- The user-facing "prompt_ru" is the main result. Write it in Russian as one natural, dense editorial/photo prompt, similar to a fashion or commercial reference description.
- Use one cohesive paragraph, not a bullet list and not a technical checklist.
- Target length for "prompt_ru": 900-1600 characters when an image has enough detail; 500-1000 characters for sparse images.
- Follow this rhythm when applicable: shot size and subject, hair/face/expression, pose and gaze, clothing and accessories with materials/textures, framing and camera angle, focus/depth of field, background/environment, lighting, color palette, contrast, visual mood, genre/style.
- Preserve the scene's real visual relationships: foreground/background separation, occlusion, visible materials, light direction, reflections, color accents, atmosphere.
- Do not add generic filler such as "8k", "masterpiece", "ultra detailed", "best quality" unless the visible style clearly calls for a short quality phrase.
- Do not use forensic, pixel-by-pixel, medical, anatomical, or identity-preservation jargon.

Prompt fields:
- "prompt_ru": polished Russian prompt in the style above.
- "prompt_en": faithful English version optimized for image generation models, also one cohesive paragraph.
- "negative_prompt": concise English list of defects to avoid.
- "model_hint": short Russian recommendation of the best model/workflow.
- "key_details": 3-7 short visible details that most affect similarity.

Strict safety rules:
- Do not identify any person.
- Do not guess names, ethnicity, nationality, private attributes, or exact age.
- You may use a broad visible age presentation only if it is visually obvious; never provide a number.
- Describe only visible visual features and user-provided creative instructions.
- Preserve subject appearance visually through neutral descriptions: face shape, hair, pose, clothing, proportions, accessories, but do not claim who the person is.
- Return only valid JSON. No markdown. No explanation.

JSON schema:
{
  "prompt_en": "Detailed English image generation prompt",
  "prompt_ru": "Natural Russian editorial-style prompt for the user",
  "negative_prompt": "Common defects to avoid",
  "model_hint": "Short Russian recommendation which model to use",
  "key_details": ["detail 1", "detail 2", "detail 3"],
  "voice_transcript": "",
  "voice_prompt_summary_ru": "",
  "voice_description_ru": "",
  "gemini_omni_prompt": ""
}
""".strip()

_DEFAULT_NEGATIVE = (
    "blurry, low quality, distorted face, bad anatomy, extra fingers, bad hands, "
    "watermark, text, logo, overexposed, underexposed, plastic skin, unnatural eyes, asymmetry"
)
_DEFAULT_HINT = (
    "Nano Banana Pro — для похожей генерации. "
    "Seedream 4.5 Edit — для редактирования по исходнику."
)


def _extract_output_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if text:
                parts.append(str(text))
    if parts:
        return "\n".join(parts).strip()
    for key in ("output_text", "text"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("Provider returned no output text")


def _extract_claude_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
            parts.append(str(block["text"]))
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError("Claude returned no text")
    return text


def _parse_json_object(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(text[start : end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("Provider returned invalid photo prompt JSON")


def _result(parsed: dict[str, Any], *, model: str) -> PromptToolProviderResult:
    prompt_en = str(parsed.get("prompt_en") or "").strip()
    prompt_ru = str(parsed.get("prompt_ru") or "").strip()
    if not prompt_en or not prompt_ru:
        raise ValueError("Provider returned incomplete photo prompt")
    key_details = parsed.get("key_details")
    payload = {
        "prompt_en": prompt_en,
        "prompt_ru": prompt_ru,
        "negative_prompt": str(parsed.get("negative_prompt") or _DEFAULT_NEGATIVE).strip(),
        "model_hint": str(parsed.get("model_hint") or _DEFAULT_HINT).strip(),
        "key_details": key_details if isinstance(key_details, list) else [],
        "voice_transcript": str(parsed.get("voice_transcript") or "").strip(),
        "voice_prompt_summary_ru": str(parsed.get("voice_prompt_summary_ru") or "").strip(),
        "voice_description_ru": str(parsed.get("voice_description_ru") or "").strip(),
        "gemini_omni_prompt": str(parsed.get("gemini_omni_prompt") or "").strip(),
    }
    return PromptToolProviderResult(model=model, payload=payload, credits_consumed=None)


def _application_error(data: dict[str, Any]) -> bool:
    try:
        code = int(data.get("code") or 0)
    except (TypeError, ValueError):
        code = 0
    message = str(data.get("msg") or data.get("message") or "").lower()
    return code >= 500 or "server exception" in message or "try again later" in message


def _claude_image_source(image_url: str) -> dict[str, str]:
    if image_url.startswith("data:image/") and "," in image_url:
        header, encoded = image_url.split(",", 1)
        media_type = header.removeprefix("data:").split(";", 1)[0]
        return {"type": "base64", "media_type": media_type, "data": encoded}
    return {"type": "url", "url": image_url}


async def _gpt(
    client: httpx.AsyncClient,
    *,
    model: str,
    image_url: str,
    user_instruction: str,
) -> PromptToolProviderResult:
    body = {
        "model": model,
        "stream": False,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_instruction},
                    {"type": "input_image", "image_url": image_url},
                ],
            },
        ],
        "reasoning": {"effort": "high"},
    }
    last_error: Exception | None = None
    for attempt in range(GPT_MAX_ATTEMPTS):
        try:
            response = await client.post("/codex/v1/responses", json=body)
            if response.status_code == 429 or response.status_code >= 500:
                raise PromptToolProviderError(f"{model} temporary HTTP {response.status_code}")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Provider response must be an object")
            if _application_error(data):
                raise PromptToolProviderError(f"{model} upstream application error")
            try:
                body_code = int(data.get("code") or 0)
            except (TypeError, ValueError):
                body_code = 0
            if body_code >= 400:
                raise PromptToolProviderError(f"{model} application error {body_code}")
            return _result(_parse_json_object(_extract_output_text(data)), model=model)
        except (httpx.HTTPError, ValueError, PromptToolProviderError) as exc:
            last_error = exc
            if attempt < GPT_MAX_ATTEMPTS - 1 and (
                isinstance(exc, httpx.HTTPError)
                or "temporary" in str(exc).lower()
                or "upstream" in str(exc).lower()
            ):
                await asyncio.sleep(2**attempt)
                continue
            break
    raise PromptToolProviderError(f"{model} photo prompt failed: {last_error}") from last_error


async def _claude(
    client: httpx.AsyncClient,
    *,
    image_url: str,
    user_instruction: str,
) -> PromptToolProviderResult:
    body = {
        "model": CLAUDE_MODEL,
        "stream": False,
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": SYSTEM_PROMPT + "\n\n" + user_instruction},
                    {"type": "image", "source": _claude_image_source(image_url)},
                ],
            }
        ],
    }
    last_error: Exception | None = None
    for attempt in range(CLAUDE_MAX_ATTEMPTS):
        try:
            response = await client.post("/claude/v1/messages", json=body)
            if response.status_code >= 500:
                raise PromptToolProviderError(f"Claude temporary HTTP {response.status_code}")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Claude response must be an object")
            return _result(_parse_json_object(_extract_claude_text(data)), model=CLAUDE_MODEL)
        except (httpx.HTTPError, ValueError, PromptToolProviderError) as exc:
            last_error = exc
            if attempt < CLAUDE_MAX_ATTEMPTS - 1 and (
                isinstance(exc, httpx.HTTPError) or "temporary" in str(exc).lower()
            ):
                await asyncio.sleep(2**attempt)
                continue
            break
    raise PromptToolProviderError(f"Claude photo prompt failed: {last_error}") from last_error


async def build_photo_prompt(
    client: httpx.AsyncClient,
    *,
    image_url: str,
    instruction: str = "",
) -> PromptToolProviderResult:
    """Run tanyapi's production photo-prompt model order on an already normalized image."""

    if not image_url:
        raise PromptToolProviderError("Photo prompt requires image_url")
    user_instruction = (
        "Analyze this image and create a precise prompt for generating a visually similar image.\n\n"
        "User goal:\nGenerate a visually similar image based on the reference.\n\n"
        "Important details to preserve:\nSubject appearance, composition, lighting, style, colors, "
        "pose, background, and camera feel.\n\n"
        + (f"Additional text instruction from user:\n{instruction.strip()}\n\n" if instruction.strip() else "")
        + "Return valid JSON only according to the required schema."
    )

    primary_error: Exception | None = None
    try:
        return await _gpt(client, model=PRIMARY_MODEL, image_url=image_url, user_instruction=user_instruction)
    except PromptToolProviderError as exc:
        primary_error = exc
    try:
        return await _gpt(client, model=FALLBACK_MODEL, image_url=image_url, user_instruction=user_instruction)
    except PromptToolProviderError as fallback_error:
        try:
            return await _claude(client, image_url=image_url, user_instruction=user_instruction)
        except PromptToolProviderError as claude_error:
            raise PromptToolProviderError(
                f"Photo prompt providers failed: {PRIMARY_MODEL}={primary_error}; "
                f"{FALLBACK_MODEL}={fallback_error}; {CLAUDE_MODEL}={claude_error}"
            ) from claude_error
