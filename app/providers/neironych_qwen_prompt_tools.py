from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import math
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.kie_prompt_tools import PromptToolProviderError, PromptToolProviderResult
from app.providers.neironych_errors import (
    NeironychProviderError,
    provider_error,
    request_identifier,
    retry_after_seconds,
)
from app.providers.nexus_prompt_tools import _chat_content, _public_https_media_url, _video_bytes
from app.providers.tanyapi_photo_prompt import (
    SYSTEM_PROMPT as PHOTO_SYSTEM_PROMPT,
    _parse_json_object,
    _result as _photo_result,
)
from app.providers.tanyapi_video_prompt import (
    VIDEO_PROMPT_MAX_DURATION_SECONDS,
    VIDEO_PROMPT_MAX_VIDEO_BYTES,
    VIDEO_SYSTEM_PROMPT,
    _extract_frame_data_urls_sync,
    _result as _video_result,
)
from app.services.video_prompt_media import probe_video_duration_seconds

logger = logging.getLogger(__name__)

QWEN_MODEL = "qwen3.8-max"
QWEN_FRAME_COUNT = 4
QWEN_TOTAL_TIMEOUT_SECONDS = 120.0
# Local resource bounds, not claims about the supplier's model/token limits.
# Four compressed 768px JPEG frames fit without persisting a source video.
QWEN_MAX_REQUEST_BYTES = 8 * 1024 * 1024
QWEN_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_FRAME_BYTES = 1024 * 1024
_TOOLS = {"image_analysis": "photo", "video_prompt": "video"}
_MAX_COMPLETION_TOKENS = {"image_analysis": 4096, "video_prompt": 8192}
_TIMEOUT = httpx.Timeout(120.0, connect=10.0, write=30.0, pool=10.0)


def _local_error() -> NeironychProviderError:
    return NeironychProviderError(
        "Qwen prompt input could not be prepared safely",
        status_code=422,
        error_code="invalid_request_contract",
        local_validation=True,
    )


def qwen_idempotency_key(task_id: uuid.UUID, tool: str) -> str:
    if not isinstance(task_id, uuid.UUID) or tool not in _TOOLS:
        raise _local_error()
    return f"ksu-prompt-{_TOOLS[tool]}-qwen38-{task_id}"


def _validate_model(model: str) -> None:
    if model != QWEN_MODEL:
        raise _local_error()


def _public_image_url(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 4000:
        raise ValueError("invalid image URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("invalid image URL")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local")):
        raise ValueError("non-public image URL")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("non-public image URL")
    # Named origins are fetched by the supplier, not this authenticated client.
    # KSU's existing media ingestion owns DNS/redirect validation for uploads.
    return value


def _jpeg_frame(value: Any) -> None:
    prefix = "data:image/jpeg;base64,"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("invalid JPEG frame")
    if len(value) > len(prefix) + ((_MAX_FRAME_BYTES + 2) // 3) * 4:
        raise ValueError("frame too large")
    raw = base64.b64decode(value[len(prefix):], validate=True)
    if not 4 <= len(raw) <= _MAX_FRAME_BYTES or not raw.startswith(b"\xff\xd8") or not raw.endswith(b"\xff\xd9"):
        raise ValueError("invalid JPEG frame")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> None:
    raise ValueError("invalid JSON number")


def _validate_body(body: str, *, tool: str, model: str) -> bytes:
    _validate_model(model)
    if tool not in _TOOLS or not isinstance(body, str) or len(body) > QWEN_MAX_REQUEST_BYTES:
        raise ValueError("invalid request identity")
    encoded = body.encode("utf-8")
    if not encoded or len(encoded) > QWEN_MAX_REQUEST_BYTES:
        raise ValueError("request too large")
    parsed = json.loads(body, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(parsed, dict) or set(parsed) != {
        "model", "stream", "messages", "max_completion_tokens"
    }:
        raise ValueError("invalid chat request")
    if (
        parsed["model"] != model or parsed["stream"] is not False
        or type(parsed["max_completion_tokens"]) is not int
        or parsed["max_completion_tokens"] != _MAX_COMPLETION_TOKENS[tool]
    ):
        raise ValueError("request tool/model changed")
    messages = parsed["messages"]
    if not isinstance(messages, list) or len(messages) != 2:
        raise ValueError("invalid chat messages")
    system, user = messages
    if (
        not isinstance(system, dict) or set(system) != {"role", "content"}
        or system["role"] != "system" or not isinstance(system["content"], str)
        or not system["content"].strip() or not isinstance(user, dict)
        or set(user) != {"role", "content"} or user["role"] != "user"
    ):
        raise ValueError("invalid chat roles")
    content = user["content"]
    if not isinstance(content, list) or not 2 <= len(content) <= QWEN_FRAME_COUNT + 1:
        raise ValueError("invalid reference count")
    text = content[0]
    if (
        not isinstance(text, dict) or set(text) != {"type", "text"}
        or text["type"] != "text" or not isinstance(text["text"], str)
        or not text["text"].strip()
    ):
        raise ValueError("invalid reference instruction")
    if tool == "image_analysis" and len(content) != 2:
        raise ValueError("photo tool requires one image")
    for item in content[1:]:
        if not isinstance(item, dict) or set(item) != {"type", "image_url"} or item["type"] != "image_url":
            raise ValueError("native video is not supported")
        image = item["image_url"]
        if not isinstance(image, dict) or set(image) != {"url"}:
            raise ValueError("invalid reference image")
        if tool == "image_analysis":
            _public_image_url(image["url"])
        else:
            _jpeg_frame(image["url"])
    return encoded


def _request_body(*, model: str, tool: str, system: str, instruction: str, images: list[str]) -> str:
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": instruction},
                    *({"type": "image_url", "image_url": {"url": image}} for image in images),
                ]},
            ],
            "max_completion_tokens": _MAX_COMPLETION_TOKENS[tool],
        },
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    _validate_body(body, tool=tool, model=model)
    return body


def _result(data: Any, *, model: str, tool: str) -> PromptToolProviderResult:
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("invalid provider response")
    parsed = _parse_json_object(_chat_content(data))
    for field in ("prompt_ru", "prompt_en"):
        if not isinstance(parsed.get(field), str) or not parsed[field].strip():
            raise ValueError("incomplete prompt pair")
    for field in (
        "negative_prompt", "model_hint", "voice_transcript", "voice_prompt_summary_ru",
        "voice_description_ru", "gemini_omni_prompt", "camera_movement_ru", "visual_style_ru",
        "audio_notes_ru",
    ):
        if field in parsed and not isinstance(parsed[field], str):
            raise ValueError("invalid prompt field")
    for field in ("key_details", "timeline_ru"):
        if field in parsed and (
            not isinstance(parsed[field], list) or any(not isinstance(item, str) for item in parsed[field])
        ):
            raise ValueError("invalid prompt list")
    if tool == "image_analysis":
        return _photo_result(parsed, model=model)
    result = _video_result(parsed, model=model)
    # This route receives still frames, never audio. A model-generated claim
    # about a soundtrack must not be presented as observed source evidence.
    result.payload["audio_notes_ru"] = ""
    return result


class NeironychQwenPromptToolsClient:
    """Prepare immutable multimodal JSON, then submit exactly once per call.

    The caller persists body/identity before submission and owns any replay.
    Neironych currently rejects native Qwen video inputs, so videos use up to
    four chronological JPEG frames through the existing bounded media helpers.
    """

    def __init__(self, api_key: str, base_url: str, *, client: httpx.AsyncClient | None = None) -> None:
        key = str(api_key or "").strip()
        if not key or "\n" in key or "\r" in key:
            raise NeironychProviderError(
                "Neironych prompt authentication is not configured",
                status_code=401, error_code="api_key_required", local_validation=True,
            )
        try:
            origin = str(base_url or "").rstrip("/")
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or not parsed.port in (None, 443)
                or any(char.isspace() for char in origin)
            ):
                raise ValueError("invalid provider origin")
        except (ValueError, TypeError):
            raise _local_error() from None
        self._url = origin + "/v1/chat/completions"
        self._authorization = f"Bearer {key}"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def prepare_image_request(
        self, *, image_url: str, instruction: str = "", model: str = QWEN_MODEL,
    ) -> str:
        try:
            async with asyncio.timeout(QWEN_TOTAL_TIMEOUT_SECONDS):
                _validate_model(model)
                public_url = _public_image_url(_public_https_media_url(image_url))
                text = (
                    "Analyze the supplied reference image and create a precise photo generation "
                    "prompt retaining visible subjects, composition, lighting, materials, pose, "
                    "background, camera style and mood. Do not identify people or infer private "
                    "attributes. "
                    + (f"Additional user instruction: {instruction.strip()}. " if instruction.strip() else "")
                    + "Return only the requested JSON schema."
                )
                return _request_body(
                    model=model, tool="image_analysis", system=PHOTO_SYSTEM_PROMPT,
                    instruction=text, images=[public_url],
                )
        except (PromptToolProviderError, ValueError, TypeError, AttributeError, OSError, TimeoutError, RecursionError):
            raise _local_error() from None

    async def prepare_video_request(
        self, *, video_url: str, instruction: str = "", duration_seconds: int | None = None,
        model: str = QWEN_MODEL,
    ) -> str:
        try:
            async with asyncio.timeout(QWEN_TOTAL_TIMEOUT_SECONDS):
                _validate_model(model)
                if duration_seconds is not None and (type(duration_seconds) is not int or duration_seconds <= 0):
                    raise ValueError("invalid requested duration")
                video = await _video_bytes(video_url)
                if not isinstance(video, bytes) or not 0 < len(video) <= VIDEO_PROMPT_MAX_VIDEO_BYTES:
                    raise ValueError("invalid video bytes")
                duration = await asyncio.to_thread(probe_video_duration_seconds, video)
                if not math.isfinite(duration) or not 0 < duration <= VIDEO_PROMPT_MAX_DURATION_SECONDS:
                    raise ValueError("invalid source duration")
                frames = await asyncio.to_thread(
                    _extract_frame_data_urls_sync, video,
                    duration_seconds=duration, max_frames=QWEN_FRAME_COUNT,
                )
                instructions = [
                    "These images are chronological frames of the same source video. Describe "
                    "visible camera and subject movement, framing, lighting, pace, composition "
                    "and temporal transitions. Do not invent audio or details invisible between frames.",
                    f"Measured source duration: {duration:g} seconds.",
                ]
                if duration_seconds is not None:
                    instructions.append(f"Requested target duration: {duration_seconds} seconds.")
                if instruction.strip():
                    instructions.append(f"Additional user instruction: {instruction.strip()}.")
                instructions.append("Return only valid JSON with all specified prompt fields.")
                return _request_body(
                    model=model, tool="video_prompt", system=VIDEO_SYSTEM_PROMPT,
                    instruction="\n\n".join(instructions), images=frames,
                )
        except (PromptToolProviderError, httpx.HTTPError, ValueError, TypeError, AttributeError, OSError, TimeoutError, RecursionError):
            raise _local_error() from None

    async def _bounded_response(self, response: httpx.Response) -> httpx.Response:
        code = "prompt_response_invalid" if response.is_success else "provider_response_invalid"

        def invalid() -> NeironychProviderError:
            return NeironychProviderError(
                "Neironych prompt response exceeds the supported contract",
                status_code=response.status_code, error_code=code,
                request_id=response.headers.get("X-Request-Id"),
            )

        # Do not decompress an unbounded supplier stream. A proxy ignoring
        # Accept-Encoding: identity must not bypass the response resource cap.
        if response.headers.get("Content-Encoding", "identity").lower().strip() != "identity":
            raise invalid()
        declared = response.headers.get("Content-Length")
        if declared is not None:
            try:
                if not 0 <= int(declared) <= QWEN_MAX_RESPONSE_BYTES:
                    raise invalid()
            except ValueError:
                raise invalid() from None
        if response.is_stream_consumed:
            content = response.content
            if len(content) > QWEN_MAX_RESPONSE_BYTES:
                raise invalid()
        else:
            content_buffer = bytearray()
            async for chunk in response.aiter_raw():
                if len(content_buffer) + len(chunk) > QWEN_MAX_RESPONSE_BYTES:
                    raise invalid()
                content_buffer.extend(chunk)
            content = bytes(content_buffer)
        return httpx.Response(response.status_code, headers=response.headers, content=content)

    async def submit(
        self, *, request_body: str, task_id: uuid.UUID, tool: str, model: str,
    ) -> PromptToolProviderResult:
        started = time.monotonic()
        status_code: int | None = None
        request_id: str | None = None
        error_code: str | None = "submission_outcome_unknown"
        try:
            try:
                key = qwen_idempotency_key(task_id, tool)
                encoded = _validate_body(request_body, tool=tool, model=model)
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                raise _local_error() from None
            async with asyncio.timeout(QWEN_TOTAL_TIMEOUT_SECONDS):
                async with self._client.stream(
                    "POST", self._url,
                    content=encoded,
                    headers={
                        "Authorization": self._authorization,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "Idempotency-Key": key,
                        "X-Client-Request-Id": str(task_id),
                        "X-Submission-Receipt": "v1",
                    },
                    timeout=_TIMEOUT, follow_redirects=False,
                ) as response:
                    status_code = response.status_code
                    request_id = request_identifier(response.headers.get("X-Request-Id"))
                    if status_code == 410:
                        # Expired replay is terminal even if a gateway sends
                        # an unreadable/compressed body. Never mint another key.
                        raise NeironychProviderError(
                            "Neironych prompt replay result has expired",
                            status_code=410, request_id=request_id,
                            error_code="idempotent_result_expired",
                            retry_after=retry_after_seconds(response.headers.get("Retry-After")),
                        )
                    bounded = await self._bounded_response(response)
                    if not bounded.is_success:
                        failure = provider_error(bounded, client_request_id=str(task_id), idempotency_key=key)
                        raise NeironychProviderError(
                            "Neironych prompt request failed",
                            status_code=failure.status_code, error_code=failure.error_code,
                            request_id=failure.request_id, retry_after=failure.retry_after,
                            local_validation=failure.local_validation,
                            submission_rejected=failure.submission_rejected,
                        ) from None
                    try:
                        result = _result(bounded.json(), model=model, tool=tool)
                    except (PromptToolProviderError, ValueError, TypeError, KeyError, IndexError, RecursionError):
                        raise NeironychProviderError(
                            "Neironych returned an invalid prompt result",
                            status_code=status_code, request_id=request_id,
                            error_code="prompt_response_invalid",
                        ) from None
            error_code = None
            return result
        except NeironychProviderError as exc:
            status_code, request_id, error_code = exc.status_code, exc.request_id, exc.error_code
            raise
        except (httpx.HTTPError, TimeoutError, OSError):
            error_code = "submission_outcome_unknown"
            raise NeironychProviderError(
                "Neironych prompt submission outcome is unknown",
                status_code=status_code, request_id=request_id, error_code=error_code,
            ) from None
        finally:
            identity = str(task_id) if isinstance(task_id, uuid.UUID) else None
            elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
            logger.info(
                "qwen_prompt_submit task_id=%s client_request_id=%s tool=%s model=%s "
                "status=%s error_code=%s provider_request_id=%s elapsed_ms=%s",
                identity, identity,
                tool if isinstance(tool, str) and tool in _TOOLS else "invalid",
                model if model == QWEN_MODEL else "invalid",
                status_code, error_code, request_id, elapsed_ms,
                extra={"http_status": status_code, "duration_ms": elapsed_ms},
            )
