from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


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

    async def create_task(
        self,
        *,
        model: str,
        input_data: dict[str, Any],
        callback_url: str = "",
    ) -> str:
        body: dict[str, Any] = {"model": model, "input": input_data}
        if callback_url:
            body["callBackUrl"] = callback_url

        response = await self._client.post("/api/v1/jobs/createTask", json=body)
        response.raise_for_status()
        payload = response.json()
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
        data = payload.get("data") or {}
        return KieTask(
            task_id=str(data.get("taskId") or task_id),
            state=str(data.get("state") or "unknown"),
            result_urls=_extract_result_urls(data),
            fail_code=str(data.get("failCode") or ""),
            fail_message=str(data.get("failMsg") or ""),
            raw=payload,
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
    if not hmac_key:
        return True
    if not task_id or not timestamp or not signature:
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
