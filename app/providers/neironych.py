from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


SEEDANCE_20_MODEL = "seedance-2.0"
SEEDANCE_25_MODEL = "seedance-2.5"
SEEDANCE_MODELS = frozenset({SEEDANCE_20_MODEL, SEEDANCE_25_MODEL})

SEEDANCE_ASPECT_RATIOS = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4", "21:9"})
SEEDANCE_20_RESOLUTIONS = frozenset({"480p", "720p", "1080p", "4k"})
SEEDANCE_25_RESOLUTIONS = frozenset({"480p", "720p", "1080p"})
SEEDANCE_20_MIN_DURATION = 4
SEEDANCE_20_MAX_DURATION = 15
SEEDANCE_25_MIN_DURATION = 4
SEEDANCE_25_MAX_DURATION = 30
SEEDANCE_20_MAX_IMAGE_REFS = 9
SEEDANCE_20_MAX_VIDEO_REFS = 3
SEEDANCE_20_MAX_AUDIO_REFS = 3
SEEDANCE_20_MAX_TOTAL_REFS = 12
SEEDANCE_25_MAX_IMAGE_REFS = 30
SEEDANCE_25_MAX_VIDEO_REFS = 10
SEEDANCE_25_MAX_AUDIO_REFS = 10
SEEDANCE_25_MAX_TOTAL_REFS = 50
SEEDANCE_MAX_PROMPT_BYTES = 40_000

_SUCCESS_STATUSES = frozenset({"succeeded", "success", "completed", "complete", "ready", "done"})
_FAILURE_STATUSES = frozenset({"failed", "failure", "error", "cancelled", "canceled"})


class NeironychProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(slots=True)
class NeironychVideoTask:
    request_id: str
    status: str
    error: str = ""
    raw: dict[str, Any] | None = None

    @property
    def succeeded(self) -> bool:
        return self.status in _SUCCESS_STATUSES

    @property
    def failed(self) -> bool:
        return self.status in _FAILURE_STATUSES


class NeironychClient:
    """Async client for the documented Neironych partner video API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.xn--e1aikcel5c5a.online",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key:
            raise NeironychProviderError("NEIRONYCH_API_KEY is not configured")
        self._authorization = f"Bearer {clean_key}"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    @staticmethod
    def _idempotency_key(value: str) -> str:
        normalized = str(value or "").strip()
        if not 8 <= len(normalized) <= 160:
            raise NeironychProviderError("Idempotency-Key must be 8-160 characters")
        return normalized

    @staticmethod
    def _prompt(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise NeironychProviderError("Seedance prompt must not be empty")
        if len(normalized.encode("utf-8")) > SEEDANCE_MAX_PROMPT_BYTES:
            raise NeironychProviderError(
                f"Seedance prompt must be at most {SEEDANCE_MAX_PROMPT_BYTES} UTF-8 bytes"
            )
        return normalized

    @staticmethod
    def _url(value: str, *, field: str) -> str:
        normalized = str(value or "").strip()
        parsed = urlsplit(normalized)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not parsed.netloc:
            raise NeironychProviderError(f"{field} must contain HTTPS URLs")
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            raise NeironychProviderError(f"{field} must not contain local URLs")
        return normalized

    @classmethod
    def _urls(
        cls,
        values: list[str] | None,
        *,
        field: str,
        maximum: int,
    ) -> list[str]:
        result: list[str] = []
        for raw in values or []:
            value = cls._url(raw, field=field)
            if value not in result:
                result.append(value)
        if len(result) > maximum:
            raise NeironychProviderError(f"{field} accepts at most {maximum} references")
        return result

    @staticmethod
    def _provider_error(response: httpx.Response, *, operation: str) -> NeironychProviderError:
        status = response.status_code
        preview = (response.text or "")[:1000]
        try:
            decoded = response.json()
        except (json.JSONDecodeError, ValueError):
            decoded = None
        message = ""
        if isinstance(decoded, dict):
            for key in ("detail", "message", "error"):
                value = decoded.get(key)
                if value:
                    message = str(value)
                    break
        if not message:
            message = preview or f"HTTP {status}"
        retryable = status in {408, 409, 425, 429} or status >= 500
        return NeironychProviderError(
            f"Neironych {operation} rejected: {message[:1000]}",
            retryable=retryable,
        )

    @classmethod
    def _validate_seedance(
        cls,
        *,
        model: str,
        duration: int | None,
        resolution: str,
        aspect_ratio: str | None,
        reference_images: list[str],
        reference_videos: list[str],
        reference_audios: list[str],
        start_image: str | None,
        end_image: str | None,
        task_type: str | None,
        generate_audio: bool | None,
    ) -> None:
        if model not in SEEDANCE_MODELS:
            raise NeironychProviderError(f"Unsupported Seedance model: {model}")

        if generate_audio is False:
            raise NeironychProviderError("Seedance audio generation cannot be disabled")

        if end_image and not start_image:
            raise NeironychProviderError("Seedance end frame requires a start frame")

        has_frames = bool(start_image or end_image)
        has_refs = bool(reference_images or reference_videos or reference_audios)
        if has_frames and has_refs:
            raise NeironychProviderError(
                "Seedance frame mode cannot be combined with reference media"
            )

        if model == SEEDANCE_20_MODEL:
            if task_type not in (None, "", "auto"):
                raise NeironychProviderError("Seedance 2.0 does not support omni reference task type")
            if resolution not in SEEDANCE_20_RESOLUTIONS:
                raise NeironychProviderError("Unsupported Seedance 2.0 resolution")
            if duration is not None and not SEEDANCE_20_MIN_DURATION <= duration <= SEEDANCE_20_MAX_DURATION:
                raise NeironychProviderError(
                    f"Seedance 2.0 duration must be {SEEDANCE_20_MIN_DURATION}-{SEEDANCE_20_MAX_DURATION} seconds"
                )
            if len(reference_images) + len(reference_videos) + len(reference_audios) > SEEDANCE_20_MAX_TOTAL_REFS:
                raise NeironychProviderError(
                    f"Seedance 2.0 accepts at most {SEEDANCE_20_MAX_TOTAL_REFS} references total"
                )
            if reference_audios and not (reference_images or reference_videos):
                raise NeironychProviderError(
                    "Seedance 2.0 audio references require an image or video reference"
                )
            allowed_ratios = set(SEEDANCE_ASPECT_RATIOS)
            if has_frames:
                allowed_ratios.add("adaptive")
            if aspect_ratio not in allowed_ratios:
                raise NeironychProviderError("Unsupported Seedance 2.0 aspect ratio")
            return

        if resolution not in SEEDANCE_25_RESOLUTIONS:
            raise NeironychProviderError("Unsupported Seedance 2.5 resolution")
        if len(reference_images) + len(reference_videos) + len(reference_audios) > SEEDANCE_25_MAX_TOTAL_REFS:
            raise NeironychProviderError(
                f"Seedance 2.5 accepts at most {SEEDANCE_25_MAX_TOTAL_REFS} references total"
            )

        normalized_task_type = str(task_type or "auto")
        if normalized_task_type not in {"auto", "reference", "edit"}:
            raise NeironychProviderError("Unsupported Seedance 2.5 omni reference task type")

        if normalized_task_type == "edit":
            if not reference_videos:
                raise NeironychProviderError("Seedance 2.5 edit requires a reference video")
            if has_frames:
                raise NeironychProviderError("Seedance 2.5 edit cannot use frame mode")
            if duration not in (None, -1):
                raise NeironychProviderError(
                    "Seedance 2.5 edit duration must follow the source video (-1 or omitted)"
                )
            if aspect_ratio not in (None, "adaptive"):
                raise NeironychProviderError(
                    "Seedance 2.5 edit aspect ratio must be adaptive or omitted"
                )
            return

        if duration is not None and not SEEDANCE_25_MIN_DURATION <= duration <= SEEDANCE_25_MAX_DURATION:
            raise NeironychProviderError(
                f"Seedance 2.5 duration must be {SEEDANCE_25_MIN_DURATION}-{SEEDANCE_25_MAX_DURATION} seconds"
            )
        if has_frames:
            if aspect_ratio not in (None, "adaptive"):
                raise NeironychProviderError(
                    "Seedance 2.5 frame mode requires adaptive aspect ratio"
                )
        elif aspect_ratio not in SEEDANCE_ASPECT_RATIOS:
            raise NeironychProviderError(
                "Seedance 2.5 text/reference mode requires a fixed aspect ratio"
            )

    async def create_seedance_video(
        self,
        *,
        model: str,
        prompt: str,
        duration: int | None,
        resolution: str,
        aspect_ratio: str | None,
        idempotency_key: str,
        reference_images: list[str] | None = None,
        reference_videos: list[str] | None = None,
        reference_audios: list[str] | None = None,
        start_image: str | None = None,
        end_image: str | None = None,
        task_type: str | None = None,
        generate_audio: bool | None = True,
    ) -> str:
        clean_prompt = self._prompt(prompt)
        clean_key = self._idempotency_key(idempotency_key)

        image_limit = (
            SEEDANCE_20_MAX_IMAGE_REFS
            if model == SEEDANCE_20_MODEL
            else SEEDANCE_25_MAX_IMAGE_REFS
        )
        video_limit = (
            SEEDANCE_20_MAX_VIDEO_REFS
            if model == SEEDANCE_20_MODEL
            else SEEDANCE_25_MAX_VIDEO_REFS
        )
        audio_limit = (
            SEEDANCE_20_MAX_AUDIO_REFS
            if model == SEEDANCE_20_MODEL
            else SEEDANCE_25_MAX_AUDIO_REFS
        )
        images = self._urls(
            reference_images,
            field="reference_images",
            maximum=image_limit,
        )
        videos = self._urls(
            reference_videos,
            field="reference_videos",
            maximum=video_limit,
        )
        audios = self._urls(
            reference_audios,
            field="reference_audios",
            maximum=audio_limit,
        )
        clean_start = self._url(start_image, field="start_image") if start_image else None
        clean_end = self._url(end_image, field="end_image") if end_image else None

        self._validate_seedance(
            model=model,
            duration=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
            reference_images=images,
            reference_videos=videos,
            reference_audios=audios,
            start_image=clean_start,
            end_image=clean_end,
            task_type=task_type,
            generate_audio=generate_audio,
        )

        body: dict[str, Any] = {
            "model": model,
            "prompt": clean_prompt,
            "resolution": resolution,
        }
        if duration is not None:
            body["duration"] = duration
        if aspect_ratio:
            body["aspect_ratio"] = aspect_ratio
        if images:
            body["reference_images"] = [{"url": value} for value in images]
        if videos:
            body["reference_videos"] = [{"url": value} for value in videos]
        if audios:
            body["reference_audios"] = [{"url": value} for value in audios]
        if clean_start:
            body["start_image"] = {"url": clean_start}
        if clean_end:
            body["end_image"] = {"url": clean_end}
        if model == SEEDANCE_25_MODEL and task_type:
            body["omni_reference_task_type"] = task_type
        if generate_audio is not None:
            body["generate_audio"] = generate_audio

        try:
            response = await self._client.post(
                "/v1/videos/generations",
                headers={
                    "Authorization": self._authorization,
                    "Idempotency-Key": clean_key,
                    "Content-Type": "application/json",
                },
                json=body,
            )
        except httpx.TransportError as exc:
            raise NeironychProviderError(
                f"Neironych create video transport error: {exc}",
                retryable=True,
            ) from exc
        if response.status_code != 202:
            raise self._provider_error(response, operation="create video")
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise NeironychProviderError(
                "Neironych create video returned invalid JSON",
                retryable=True,
            ) from exc
        request_id = payload.get("request_id") if isinstance(payload, dict) else None
        if not request_id:
            raise NeironychProviderError(
                f"Neironych create video returned no request_id: {payload!r}",
                retryable=True,
            )
        return str(request_id)

    async def get_video(self, request_id: str) -> NeironychVideoTask:
        clean_id = str(request_id or "").strip()
        if not clean_id:
            raise NeironychProviderError("Neironych request_id must not be empty")
        try:
            response = await self._client.get(
                f"/v1/videos/{clean_id}",
                headers={"Authorization": self._authorization},
            )
        except httpx.TransportError as exc:
            raise NeironychProviderError(
                f"Neironych video status transport error: {exc}",
                retryable=True,
            ) from exc
        if not response.is_success:
            raise self._provider_error(response, operation="video status")
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise NeironychProviderError(
                "Neironych video status returned invalid JSON",
                retryable=True,
            ) from exc
        if not isinstance(payload, dict):
            raise NeironychProviderError(
                "Neironych video status returned invalid payload",
                retryable=True,
            )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        status = str(data.get("status") or payload.get("status") or "unknown").strip().lower()
        error = ""
        for source in (data, payload):
            for key in ("error", "message", "detail"):
                value = source.get(key)
                if value:
                    error = str(value)[:1000]
                    break
            if error:
                break
        return NeironychVideoTask(
            request_id=str(data.get("request_id") or payload.get("request_id") or clean_id),
            status=status,
            error=error,
            raw=payload,
        )

    async def download_video(
        self,
        request_id: str,
        target: Path,
        *,
        max_bytes: int = 1024 * 1024 * 1024,
    ) -> Path:
        clean_id = str(request_id or "").strip()
        if not clean_id:
            raise NeironychProviderError("Neironych request_id must not be empty")
        target.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            async with self._client.stream(
                "GET",
                f"/v1/videos/{clean_id}/content",
                headers={"Authorization": self._authorization, "Accept": "video/mp4,*/*"},
            ) as response:
                if not response.is_success:
                    body = await response.aread()
                    preview = body[:1000].decode("utf-8", errors="replace")
                    retryable = response.status_code in {408, 409, 425, 429} or response.status_code >= 500
                    raise NeironychProviderError(
                        f"Neironych video content rejected: {preview or response.status_code}",
                        retryable=retryable,
                    )
                declared = response.headers.get("content-length")
                if declared:
                    try:
                        if int(declared) > max_bytes:
                            raise NeironychProviderError(
                                "Neironych video result exceeds configured download limit"
                            )
                    except ValueError:
                        pass
                with target.open("wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > max_bytes:
                            raise NeironychProviderError(
                                "Neironych video result exceeds configured download limit"
                            )
                        output.write(chunk)
        except NeironychProviderError:
            target.unlink(missing_ok=True)
            raise
        except (httpx.TransportError, OSError) as exc:
            target.unlink(missing_ok=True)
            raise NeironychProviderError(
                f"Neironych video content download failed: {exc}",
                retryable=True,
            ) from exc
        if total <= 0:
            target.unlink(missing_ok=True)
            raise NeironychProviderError(
                "Neironych video content is empty",
                retryable=True,
            )
        return target
