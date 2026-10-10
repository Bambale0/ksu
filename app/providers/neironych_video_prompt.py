from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx

from app.providers.kie_prompt_tools import PromptToolProviderError, PromptToolProviderResult
from app.providers.nexus_prompt_tools import _video_bytes
from app.providers.tanyapi_photo_prompt import _extract_output_text
from app.providers.tanyapi_video_prompt import (
    VIDEO_SYSTEM_PROMPT,
    _extract_frame_data_urls_sync,
    _frame_content,
    _parse_video_json_object,
    _result,
)
from app.services.video_prompt_media import probe_video_duration_seconds

GROK45_MODEL = "grok-4.5"
GROK45_FRAME_COUNT = 4
GROK45_REQUEST_PREFIX = "ksu-video-prompt-grok45-"


class NeironychVideoPromptClient:
    """Describe a source video through Grok 4.5 Responses Vision on Neironych.

    Grok 4.5 exposes vision, not a documented native video-file input. We sample
    representative frames from safely fetched media and send them as input_image
    data URLs. One task has one stable Neironych idempotency key even if our
    queue reclaims an outbox lease after a process crash.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.xn--e1aikcel5c5a.online",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key:
            raise PromptToolProviderError("NEIRONYCH_API_KEY is not configured")
        self._owns_client = client is None
        self._authorization = f"Bearer {clean_key}"
        self._client = client or httpx.AsyncClient(
            base_url=str(base_url or "").rstrip("/"),
            timeout=httpx.Timeout(120.0, connect=10.0),
            follow_redirects=False,
            trust_env=False,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def build_video_prompt(
        self,
        *,
        video_url: str,
        instruction: str = "",
        duration_seconds: int | None = None,
        idempotency_key: str,
    ) -> PromptToolProviderResult:
        try:
            request_id = str(uuid.UUID(str(idempotency_key)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise PromptToolProviderError("A valid task UUID is required for video prompt") from exc

        video_data = await _video_bytes(video_url)
        actual_duration = await asyncio.to_thread(
            probe_video_duration_seconds, video_data
        )
        if actual_duration <= 0:
            raise PromptToolProviderError("Видео имеет некорректную длительность")
        frame_urls = await asyncio.to_thread(
            _extract_frame_data_urls_sync,
            video_data,
            duration_seconds=actual_duration,
            max_frames=GROK45_FRAME_COUNT,
        )

        extras = [
            "Analyze the attached representative video frames in chronological order.",
            "These frames were sampled from the source video; infer motion and camera "
            "trajectory cautiously and do not invent audio that cannot be heard.",
            f"Measured source video duration: {actual_duration:g} seconds.",
        ]
        if duration_seconds:
            extras.append(f"Requested target duration: {int(duration_seconds)} seconds.")
        if instruction.strip():
            extras.append(f"Additional user instruction: {instruction.strip()}")
        extras.append("Return valid JSON only with the fields specified in the system message.")
        body: dict[str, Any] = {
            "model": GROK45_MODEL,
            "stream": False,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": VIDEO_SYSTEM_PROMPT}],
                },
                {
                    "role": "user",
                    "content": _frame_content(
                        user_instruction="\n\n".join(extras),
                        frame_data_urls=frame_urls,
                    ),
                },
            ],
            "reasoning": {"effort": "high"},
            "max_output_tokens": 4096,
        }
        try:
            response = await self._client.post(
                "/v1/responses",
                headers={
                    "Authorization": self._authorization,
                    "Idempotency-Key": GROK45_REQUEST_PREFIX + request_id,
                    "X-Client-Request-Id": request_id,
                },
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Neironych response must be an object")
            status = str(data.get("status") or "completed")
            if status != "completed":
                raise PromptToolProviderError(f"Grok 4.5 response status: {status}")
            if data.get("error"):
                raise PromptToolProviderError("Grok 4.5 returned a provider error")
            return _result(
                _parse_video_json_object(_extract_output_text(data)),
                model=GROK45_MODEL,
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise PromptToolProviderError(
                f"Grok 4.5 video prompt failed: {exc}"
            ) from exc
