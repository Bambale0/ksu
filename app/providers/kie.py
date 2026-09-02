from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.kie_image_contracts import normalize_kie_image_input
from app.services.kie_video_contracts import normalize_kie_video_input
from app.services.seedance_reference_modes import enforce_seedance_reference_mode


class KieProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class KieTask:
    task_id: str
    state: str
    result_urls: list[str]
    fail_code: str = ""
    fail_message: str = ""
    raw: dict[str, Any] | None = None
    tracks: list[dict[str, Any]] | None = None


class KieClient:
    def __init__(self, api_key: str, base_url: str = "https://api.kie.ai") -> None:
        if not api_key:
            raise KieProviderError("KIE_API_KEY is not configured")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _require_success_payload(payload: dict[str, Any], *, operation: str) -> None:
        raw_code = payload.get("code")
        if raw_code is None:
            return
        try:
            code = int(raw_code)
        except (TypeError, ValueError) as exc:
            raise KieProviderError(f"Kie {operation} returned invalid code: {payload!r}") from exc
        if code != 200:
            message = payload.get("msg") or payload.get("message") or payload
            raise KieProviderError(f"Kie {operation} rejected: {message!r}")

    async def create_task(
        self,
        *,
        model: str,
        input_data: dict[str, Any],
        callback_url: str = "",
    ) -> str:
        normalized_input = normalize_kie_image_input(model, input_data)
        normalized_input = normalize_kie_video_input(model, normalized_input)
        enforce_seedance_reference_mode(model, normalized_input)
        body: dict[str, Any] = {"model": model, "input": normalized_input}
        if callback_url:
            body["callBackUrl"] = callback_url

        response = await self._client.post("/api/v1/jobs/createTask", json=body)
        response.raise_for_status()
        payload = response.json()
        self._require_success_payload(payload, operation="createTask")
        task_id = (payload.get("data") or {}).get("taskId")
        if not task_id:
            raise KieProviderError(f"Kie createTask returned no taskId: {payload!r}")
        return str(task_id)

    async def get_task(self, task_id: str) -> KieTask:
        response = await self._client.get(
            "/api/v1/jobs/recordInfo",
            params={"taskId": task_id},
        )
        response.raise_for_status()
        payload = response.json()
        self._require_success_payload(payload, operation="recordInfo")
        data = payload.get("data") or {}
        return KieTask(
            task_id=str(data.get("taskId") or task_id),
            state=str(data.get("state") or "unknown"),
            result_urls=_extract_result_urls(data),
            fail_code=str(data.get("failCode") or ""),
            fail_message=str(data.get("failMsg") or ""),
            raw=payload,
        )

    async def create_music_task(
        self,
        *,
        model: str,
        input_data: dict[str, Any],
        callback_url: str = "",
    ) -> str:
        body = dict(input_data)
        if body.get("customMode") is True and not str(body.get("title") or "").strip():
            body["title"] = "ROXY Track"
        body["model"] = model
        if callback_url:
            body["callBackUrl"] = callback_url
        response = await self._client.post("/api/v1/generate", json=body)
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 200:
            raise KieProviderError(
                f"Kie music generation rejected: {payload.get('msg') or payload!r}"
            )
        task_id = (payload.get("data") or {}).get("taskId")
        if not task_id:
            raise KieProviderError(f"Kie music generation returned no taskId: {payload!r}")
        return str(task_id)

    async def get_music_task(self, task_id: str) -> KieTask:
        response = await self._client.get(
            "/api/v1/generate/record-info",
            params={"taskId": task_id},
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 200:
            raise KieProviderError(f"Kie music record-info failed: {payload.get('msg') or payload!r}")
        data = payload.get("data") or {}
        provider_status = str(data.get("status") or "PENDING").upper()
        tracks = _extract_music_tracks(data)
        if provider_status == "SUCCESS":
            state = "success"
        elif provider_status in {
            "CREATE_TASK_FAILED",
            "GENERATE_AUDIO_FAILED",
            "CALLBACK_EXCEPTION",
            "SENSITIVE_WORD_ERROR",
        }:
            state = "fail"
        else:
            state = "generating"
        return KieTask(
            task_id=str(data.get("taskId") or task_id),
            state=state,
            result_urls=[str(item["audio_url"]) for item in tracks if item.get("audio_url")],
            fail_code=str(data.get("errorCode") or ""),
            fail_message=str(data.get("errorMessage") or ""),
            raw=payload,
            tracks=tracks,
        )


def extract_kie_task_id(payload: dict[str, Any]) -> str:
    data = payload.get("data")
    if isinstance(data, dict):
        task_id = data.get("taskId") or data.get("task_id")
        if task_id:
            return str(task_id)
    task_id = payload.get("taskId") or payload.get("task_id")
    return str(task_id or "")


def verify_kie_webhook(
    *,
    task_id: str,
    timestamp: str | None,
    signature: str | None,
    hmac_key: str,
    max_age_seconds: int = 300,
) -> bool:
    """Verify the official KIE taskId.timestamp HMAC and fail closed without a key."""

    if not hmac_key or not task_id or not timestamp or not signature:
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - sent_at) > max_age_seconds:
        return False

    message = f"{task_id}.{timestamp}".encode()
    digest = hmac.new(hmac_key.encode(), message, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


def kie_generation_binding(generation_id: uuid.UUID, hmac_key: str) -> str:
    """Sign the local generation recovery hint without exposing the webhook secret."""

    if not hmac_key:
        raise ValueError("KIE webhook HMAC key is not configured")
    message = f"roxy:kie-callback:v1:{generation_id}".encode("ascii")
    digest = hmac.new(hmac_key.encode(), message, hashlib.sha256).digest()[:18]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def verify_kie_generation_binding(
    generation_id: uuid.UUID,
    binding: str | None,
    hmac_key: str,
) -> bool:
    if not binding or not hmac_key:
        return False
    expected = kie_generation_binding(generation_id, hmac_key)
    return hmac.compare_digest(expected, binding)


def _extract_music_tracks(data: dict[str, Any]) -> list[dict[str, Any]]:
    response = data.get("response")
    rows = response.get("sunoData") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        rows = data.get("data") if isinstance(data.get("data"), list) else []
    tracks: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        audio_url = raw.get("audioUrl") or raw.get("audio_url")
        stream_url = raw.get("streamAudioUrl") or raw.get("stream_audio_url")
        image_url = raw.get("imageUrl") or raw.get("image_url")
        duration = raw.get("duration")
        try:
            normalized_duration = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            normalized_duration = None
        tracks.append(
            {
                "id": str(raw.get("id") or ""),
                "audio_url": str(audio_url or ""),
                "stream_audio_url": str(stream_url or ""),
                "image_url": str(image_url or ""),
                "prompt": str(raw.get("prompt") or ""),
                "model_name": str(raw.get("modelName") or raw.get("model_name") or ""),
                "title": str(raw.get("title") or ""),
                "tags": str(raw.get("tags") or ""),
                "duration": normalized_duration,
                "create_time": str(raw.get("createTime") or raw.get("create_time") or ""),
            }
        )
    return tracks


def _extract_result_urls(data: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []

    result_json = data.get("resultJson")
    if isinstance(result_json, str) and result_json:
        try:
            decoded = json.loads(result_json)
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            candidates.extend(_urls_from_mapping(decoded))

    info = data.get("info")
    if isinstance(info, dict):
        candidates.extend(_urls_from_mapping(info))

    candidates.extend(_urls_from_mapping(data))

    result: list[str] = []
    for item in candidates:
        if isinstance(item, str) and item.startswith(("http://", "https://")) and item not in result:
            result.append(item)
    return result


def _urls_from_mapping(payload: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    for key in (
        "resultUrls",
        "result_urls",
        "urls",
        "originUrls",
        "video_url",
        "image_url",
        "audio_url",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif value is not None:
            values.append(value)
    return values
