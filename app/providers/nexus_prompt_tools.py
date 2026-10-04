from __future__ import annotations

import asyncio
import contextlib
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.core.config import settings
from app.providers.kie_prompt_tools import (
    GPT_PROMPT_MAX_ATTEMPTS,
    PromptToolProviderError,
    PromptToolProviderResult,
    _PROMPT_SYSTEM,
    _gpt_prompt_builder_user_text,
    _parse_json_object,
    _prompt_pair,
)
from app.providers.tanyapi_photo_prompt import (
    GPT_MAX_ATTEMPTS,
    SYSTEM_PROMPT as PHOTO_SYSTEM_PROMPT,
    _parse_json_object as _parse_photo_json_object,
    _result as _photo_result,
)
from app.providers.tanyapi_video_prompt import (
    VIDEO_PROMPT_MAX_VIDEO_BYTES,
    VIDEO_SYSTEM_PROMPT,
    _extract_frame_jpeg_bytes_sync,
    _parse_video_json_object,
    _result as _video_result,
)
from app.services.feed_static import FeedStaticStorage
from app.services.media_assets import MediaIngestService, UnsafeMediaSource
from app.services.reference_static import ReferenceStaticStorage
from app.services.video_prompt_media import probe_video_duration_seconds

GPT55_MODEL = "gpt-5.5"
NEXUS_VISION_MODEL = "gpt-6-sol"
NEXUS_VISION_MAX_IMAGES = 4
PROMPT_FRAME_STALE_SECONDS = 15 * 60
_REDIRECT_CODES = {301, 302, 303, 307, 308}


def _chat_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Nexus chat returned no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ValueError("Nexus chat returned no assistant message")
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
    raise ValueError("Nexus chat returned empty content")


def _local_media_path(value: str) -> Path | None:
    clean = str(value or "").strip()
    parsed = urlsplit(clean)
    if parsed.scheme or parsed.netloc:
        base = urlsplit(settings.public_base_url.strip())
        if (
            parsed.scheme.lower() != base.scheme.lower()
            or parsed.netloc.lower() != base.netloc.lower()
        ):
            return None
    return ReferenceStaticStorage.path_for_url(clean) or FeedStaticStorage.path_for_url(clean)


def _public_https_media_url(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise PromptToolProviderError("media URL is required")

    if _local_media_path(clean) is not None:
        source = urlsplit(clean)
        path = source.path if source.scheme else clean.split("?", 1)[0]
        base = urlsplit(settings.public_base_url.strip())
        if base.scheme != "https" or not base.netloc:
            raise PromptToolProviderError(
                "PUBLIC_BASE_URL must be public HTTPS for Nexus vision"
            )
        return urlunsplit((base.scheme, base.netloc, path, "", ""))

    parsed = urlsplit(clean)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise PromptToolProviderError("Nexus vision requires a public HTTPS media URL")
    return clean


def cleanup_stale_prompt_frames(
    *,
    max_age_seconds: int = PROMPT_FRAME_STALE_SECONDS,
) -> int:
    root = ReferenceStaticStorage.ensure_root() / "prompt-frames"
    if not root.is_dir():
        return 0
    cutoff = time.time() - max(60, int(max_age_seconds))
    removed = 0
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            if child.stat().st_mtime >= cutoff:
                continue
        except OSError:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed += 1
    try:
        root.rmdir()
    except OSError:
        pass
    return removed


@contextlib.contextmanager
def _published_prompt_frames(frame_bytes: list[bytes]) -> Iterator[list[str]]:
    if not frame_bytes:
        raise PromptToolProviderError("video frame list is empty")
    if len(frame_bytes) > NEXUS_VISION_MAX_IMAGES:
        raise PromptToolProviderError(
            f"Nexus vision accepts at most {NEXUS_VISION_MAX_IMAGES} frames"
        )

    base = urlsplit(settings.public_base_url.strip())
    if base.scheme != "https" or not base.netloc:
        raise PromptToolProviderError(
            "PUBLIC_BASE_URL must be public HTTPS for Nexus video analysis"
        )

    cleanup_stale_prompt_frames()
    session_id = uuid.uuid4().hex
    relative_dir = Path("prompt-frames") / session_id
    target_dir = ReferenceStaticStorage.ensure_root() / relative_dir
    target_dir.mkdir(parents=True, exist_ok=False)
    urls: list[str] = []
    try:
        for index, data in enumerate(frame_bytes, start=1):
            if not data:
                raise PromptToolProviderError("video frame is empty")
            path = target_dir / f"frame-{index:02d}.jpg"
            path.write_bytes(data)
            try:
                path.chmod(0o644)
            except OSError:
                pass
            urls.append(
                ReferenceStaticStorage.public_url(
                    (relative_dir / path.name).as_posix()
                )
            )
        yield urls
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)
        try:
            target_dir.parent.rmdir()
        except OSError:
            pass


async def _download_public_video(url: str) -> bytes:
    current = _public_https_media_url(url)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=90.0, write=10.0, pool=10.0),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "roxy-nexus-prompt-media/1.0"},
        ) as client:
            for _ in range(4):
                await MediaIngestService._validate_public_https_url(current)
                async with client.stream("GET", current) as response:
                    if response.status_code in _REDIRECT_CODES:
                        location = response.headers.get("location")
                        if not location:
                            raise PromptToolProviderError(
                                "video redirect has no Location header"
                            )
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    declared = response.headers.get("content-length")
                    if declared:
                        try:
                            if int(declared) > VIDEO_PROMPT_MAX_VIDEO_BYTES:
                                raise PromptToolProviderError(
                                    "Видео слишком большое для Nexus prompt analysis"
                                )
                        except ValueError as exc:
                            raise PromptToolProviderError(
                                "video returned invalid Content-Length"
                            ) from exc

                    data = bytearray()
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        data.extend(chunk)
                        if len(data) > VIDEO_PROMPT_MAX_VIDEO_BYTES:
                            raise PromptToolProviderError(
                                "Видео слишком большое для Nexus prompt analysis"
                            )
                    if not data:
                        raise PromptToolProviderError("Видео пустое")
                    return bytes(data)
    except PromptToolProviderError:
        raise
    except (httpx.HTTPError, UnsafeMediaSource) as exc:
        raise PromptToolProviderError(
            f"Не удалось скачать видео для Nexus prompt analysis: {exc}"
        ) from exc
    raise PromptToolProviderError("Too many video redirects")


async def _video_bytes(video_url: str) -> bytes:
    local_path = _local_media_path(video_url)
    if local_path is not None and local_path.is_file():
        size = local_path.stat().st_size
        if size <= 0:
            raise PromptToolProviderError("Видео пустое")
        if size > VIDEO_PROMPT_MAX_VIDEO_BYTES:
            raise PromptToolProviderError("Видео слишком большое для Nexus prompt analysis")
        return await asyncio.to_thread(local_path.read_bytes)
    return await _download_public_video(video_url)


class NexusPromptToolsClient:
    """Nexus prompt tools: GPT-5.5 text and GPT-6 Sol vision."""

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
            timeout=httpx.Timeout(120.0, connect=10.0),
            headers={"Authorization": f"Bearer {clean_key}"},
        )
        self._authorization = f"Bearer {clean_key}"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _post_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(
            "/v1/chat/completions",
            headers={"Authorization": self._authorization},
            json=body,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Nexus chat response must be an object")
        return data

    async def build_prompt(
        self,
        *,
        text: str,
        image_url: str | None = None,
    ) -> PromptToolProviderResult:
        if image_url:
            return await self.analyze_image(image_url=image_url, instruction=text)

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
                data = await self._post_chat(body)
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

    async def analyze_image(
        self,
        *,
        image_url: str,
        instruction: str = "",
    ) -> PromptToolProviderResult:
        public_url = _public_https_media_url(image_url)
        user_instruction = (
            "Analyze this image and create a precise prompt for generating a visually similar image.\n\n"
            "User goal:\nGenerate a visually similar image based on the reference.\n\n"
            "Important details to preserve:\nSubject appearance, composition, lighting, style, colors, "
            "pose, background, and camera feel.\n\n"
            + (
                f"Additional text instruction from user:\n{instruction.strip()}\n\n"
                if instruction.strip()
                else ""
            )
            + "Return valid JSON only according to the required schema."
        )
        body: dict[str, Any] = {
            "model": NEXUS_VISION_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": PHOTO_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_instruction},
                        {"type": "image_url", "image_url": {"url": public_url}},
                    ],
                },
            ],
            "reasoning_effort": "medium",
            "max_completion_tokens": 3072,
        }

        last_error: Exception | None = None
        for attempt in range(GPT_MAX_ATTEMPTS):
            try:
                data = await self._post_chat(body)
                return _photo_result(
                    _parse_photo_json_object(_chat_content(data)),
                    model=NEXUS_VISION_MODEL,
                )
            except (httpx.HTTPError, ValueError, PromptToolProviderError) as exc:
                last_error = exc
                if attempt >= GPT_MAX_ATTEMPTS - 1:
                    break
                content = list(body["messages"][1]["content"])
                content[0] = {
                    "type": "text",
                    "text": (
                        f"{user_instruction}\n\n"
                        "Previous response was invalid. Return only the required JSON object."
                    ),
                }
                body = {
                    **body,
                    "messages": [
                        body["messages"][0],
                        {"role": "user", "content": content},
                    ],
                }
        raise PromptToolProviderError(
            f"Nexus image prompt failed: {last_error or 'unknown error'}"
        ) from last_error

    async def build_video_prompt(
        self,
        *,
        video_url: str,
        instruction: str = "",
        duration_seconds: int | None = None,
    ) -> PromptToolProviderResult:
        del duration_seconds
        data = await _video_bytes(video_url)
        actual_duration = await asyncio.to_thread(probe_video_duration_seconds, data)
        frames = await asyncio.to_thread(
            _extract_frame_jpeg_bytes_sync,
            data,
            duration_seconds=actual_duration,
            max_frames=NEXUS_VISION_MAX_IMAGES,
        )

        extras: list[str] = []
        if instruction.strip():
            extras.append(f"Additional text instruction from user:\n{instruction.strip()}")
        extras.append(f"Measured clip duration: {actual_duration:g} seconds.")
        user_instruction = (
            "Analyze the attached representative frames sampled from a source video in chronological "
            "order and create a detailed prompt for generating a visually similar video.\n\n"
            "Infer camera movement, subject motion, pacing and transitions from frame-to-frame "
            "differences. Preserve visible subject, framing, lighting, color, environment and mood. "
            "Do not invent unavailable audio.\n\n"
            + "\n\n".join(extras)
            + "\n\nReturn valid JSON only according to the required schema."
        )

        with _published_prompt_frames(frames) as frame_urls:
            content: list[dict[str, Any]] = [
                {"type": "text", "text": user_instruction}
            ]
            content.extend(
                {
                    "type": "image_url",
                    "image_url": {"url": frame_url},
                }
                for frame_url in frame_urls
            )
            body: dict[str, Any] = {
                "model": NEXUS_VISION_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": VIDEO_SYSTEM_PROMPT},
                    {"role": "user", "content": content},
                ],
                "reasoning_effort": "high",
                "max_completion_tokens": 4096,
            }

            last_error: Exception | None = None
            for attempt in range(GPT_MAX_ATTEMPTS):
                try:
                    response = await self._post_chat(body)
                    return _video_result(
                        _parse_video_json_object(_chat_content(response)),
                        model=NEXUS_VISION_MODEL,
                    )
                except (httpx.HTTPError, ValueError, PromptToolProviderError) as exc:
                    last_error = exc
                    if attempt >= GPT_MAX_ATTEMPTS - 1:
                        break
                    retry_content = list(content)
                    retry_content[0] = {
                        "type": "text",
                        "text": (
                            f"{user_instruction}\n\n"
                            "Previous response was invalid. Return only the required JSON object."
                        ),
                    }
                    body = {
                        **body,
                        "messages": [
                            body["messages"][0],
                            {"role": "user", "content": retry_content},
                        ],
                    }

        raise PromptToolProviderError(
            f"Nexus video prompt failed: {last_error or 'unknown error'}"
        ) from last_error
