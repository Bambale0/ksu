from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx

from app.providers.kie_prompt_tools import PromptToolProviderError, PromptToolProviderResult
from app.providers.nexus_prompt_tools import _chat_content, _public_https_media_url, _video_bytes
from app.providers.tanyapi_photo_prompt import (
    SYSTEM_PROMPT as PHOTO_SYSTEM_PROMPT,
    _parse_json_object,
    _result as _photo_result,
)
from app.providers.tanyapi_video_prompt import (
    VIDEO_SYSTEM_PROMPT,
    _extract_frame_data_urls_sync,
    _result as _video_result,
)
from app.services.video_prompt_media import probe_video_duration_seconds

QWEN_MODEL = "qwen3.8-max"
QWEN_FRAME_COUNT = 4
_QWEN_IDEMPOTENCY_PREFIX = "ksu-prompt-"


class NeironychQwenPromptToolsClient:
    """Neironych Qwen 3.8 Max via multimodal OpenAI-compatible Chat Completions.

    Image uses the existing public HTTPS reference route. Video is read
    through the established safe media loader and represented by four
    chronological, compressed JPEG frames; no undocumented native-video
    Qwen input is assumed. Supplier requests have a task-scoped stable
    idempotency key and are never automatically reissued in this client.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.xn--e1aikcel5c5a.online",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        key = str(api_key or "").strip()
        if not key:
            raise PromptToolProviderError("NEIRONYCH_API_KEY is not configured")
        self._authorization = f"Bearer {key}"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=str(base_url or "").rstrip("/"),
            timeout=httpx.Timeout(120.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _analyze(
        self,
        *,
        tool: str,
        system_prompt: str,
        user_text: str,
        image_urls: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        try:
            task_id = str(uuid.UUID(str(idempotency_key)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise PromptToolProviderError("A valid task UUID is required") from exc
        if not image_urls:
            raise PromptToolProviderError("Qwen reference image is required")
        payload: dict[str, Any] = {
            "model": QWEN_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        *(
                            {"type": "image_url", "image_url": {"url": source}}
                            for source in image_urls
                        ),
                    ],
                },
            ],
            "max_completion_tokens": 8192 if tool == "video" else 4096,
        }
        try:
            response = await self._client.post(
                "/v1/chat/completions",
                headers={
                    "Authorization": self._authorization,
                    "Idempotency-Key": (
                        f"{_QWEN_IDEMPOTENCY_PREFIX}{tool}-qwen38-{task_id}"
                    ),
                    "X-Client-Request-Id": task_id,
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or body.get("error"):
                raise ValueError("Qwen chat returned an invalid provider response")
            # Reject free-form hallucinations: the two ROXY customer prompts
            # must be present before any completed/charged task is recorded.
            parsed = _parse_json_object(_chat_content(body))
            if not str(parsed.get("prompt_ru") or "").strip() or not str(
                parsed.get("prompt_en") or ""
            ).strip():
                raise ValueError("Qwen chat returned incomplete prompt JSON")
            return parsed
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            raise PromptToolProviderError(
                f"Qwen 3.8 {tool} prompt failed: {type(exc).__name__}"
            ) from exc

    async def analyze_image(
        self, *, image_url: str, instruction: str = "", idempotency_key: str
    ) -> PromptToolProviderResult:
        validated_url = _public_https_media_url(image_url)
        user_instruction = (
            "Analyze the supplied reference image and create a precise photo "
            "generation prompt retaining visible subjects, composition, "
            "lighting, materials, pose, background, camera style and mood. "
            "Do not identify people or infer private attributes. "
            + (
                f"Additional user instruction: {instruction.strip()}. "
                if instruction.strip()
                else ""
            )
            + "Return only the requested JSON schema."
        )
        parsed = await self._analyze(
            tool="photo",
            system_prompt=PHOTO_SYSTEM_PROMPT,
            user_text=user_instruction,
            image_urls=[validated_url],
            idempotency_key=idempotency_key,
        )
        return _photo_result(parsed, model=QWEN_MODEL)

    async def build_video_prompt(
        self,
        *,
        video_url: str,
        instruction: str = "",
        duration_seconds: int | None = None,
        idempotency_key: str,
    ) -> PromptToolProviderResult:
        video_data = await _video_bytes(video_url)
        actual_duration = await asyncio.to_thread(
            probe_video_duration_seconds, video_data
        )
        if actual_duration <= 0:
            raise PromptToolProviderError("Видео имеет некорректную длительность")
        frames = await asyncio.to_thread(
            _extract_frame_data_urls_sync,
            video_data,
            duration_seconds=actual_duration,
            max_frames=QWEN_FRAME_COUNT,
        )
        user_instructions = [
            "These images are chronological frames of the same source video. "
            "Describe visible camera and subject movement, framing, lighting, "
            "pace, composition and temporal transitions. Do not invent audio "
            "or details invisible between frames.",
            f"Measured source duration: {actual_duration:g} seconds.",
        ]
        if duration_seconds:
            user_instructions.append(
                f"Requested target duration: {int(duration_seconds)} seconds."
            )
        if instruction.strip():
            user_instructions.append(
                f"Additional user instruction: {instruction.strip()}."
            )
        user_instructions.append("Return only valid JSON with all specified prompt fields.")
        parsed = await self._analyze(
            tool="video",
            system_prompt=VIDEO_SYSTEM_PROMPT,
            user_text="\n\n".join(user_instructions),
            image_urls=frames,
            idempotency_key=idempotency_key,
        )
        return _video_result(parsed, model=QWEN_MODEL)
