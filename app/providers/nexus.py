from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


class NexusProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class NexusTask:
    task_id: str
    status: str
    image_urls: list[str]
    error: str = ""
    raw: dict[str, Any] | None = None


class NexusClient:
    """Small async client for the documented NexusAPI /generate + /tasks flow."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://nexusapi.dev",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        clean_key = api_key.strip()
        if not clean_key:
            raise NexusProviderError("NEXUS_API_KEY is not configured")
        self._authorization = f"Bearer {clean_key}"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def create_nano_banana_pro(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "1:1",
        image_size: str = "2K",
        idempotency_key: str | None = None,
    ) -> str:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise NexusProviderError("Prompt must not be empty")
        if aspect_ratio not in {"1:1", "16:9", "9:16", "4:3", "3:4"}:
            raise NexusProviderError("Unsupported Nano Banana Pro aspect ratio")
        if image_size not in {"1K", "2K", "4K"}:
            raise NexusProviderError("Unsupported Nano Banana Pro image size")

        response = await self._client.post(
            "/generate",
            headers={
                "Authorization": self._authorization,
                "Idempotency-Key": idempotency_key or str(uuid.uuid4()),
            },
            json={
                "params": {
                    "model_name": "nano-banana-pro",
                    "prompt": clean_prompt,
                    "aspect_ratio": aspect_ratio,
                    "image_size": image_size,
                }
            },
        )
        response.raise_for_status()
        payload = response.json()
        task_id = payload.get("task_id")
        if not task_id:
            raise NexusProviderError(f"NexusAPI /generate returned no task_id: {payload!r}")
        return str(task_id)

    async def get_task(self, task_id: str) -> NexusTask:
        response = await self._client.get(
            f"/tasks/{task_id}",
            headers={"Authorization": self._authorization},
        )
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status") or "unknown").lower()
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        image_urls = _extract_image_urls(result)
        return NexusTask(
            task_id=str(payload.get("task_id") or payload.get("id") or task_id),
            status=status,
            image_urls=image_urls,
            error=_extract_error(payload.get("error")),
            raw=payload,
        )

    async def wait_for_task(
        self,
        task_id: str,
        *,
        timeout_seconds: float = 90.0,
        poll_interval_seconds: float = 2.0,
    ) -> NexusTask:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() < deadline:
            task = await self.get_task(task_id)
            if task.status == "completed":
                if not task.image_urls:
                    raise NexusProviderError(
                        f"NexusAPI task {task_id} completed without image URL"
                    )
                return task
            if task.status == "failed":
                raise NexusProviderError(task.error or f"NexusAPI task {task_id} failed")
            await asyncio.sleep(poll_interval_seconds)
        raise NexusProviderError(f"NexusAPI task {task_id} timed out")


def _extract_image_urls(result: dict[str, Any]) -> list[str]:
    candidates: list[Any] = []
    image_urls = result.get("image_urls")
    if isinstance(image_urls, list):
        candidates.extend(image_urls)
    image_url = result.get("image_url")
    if image_url:
        candidates.append(image_url)

    urls: list[str] = []
    for raw in candidates:
        value = str(raw or "").strip()
        if value.startswith(("https://", "http://")) and value not in urls:
            urls.append(value)
    return urls


def _extract_error(raw: Any) -> str:
    if isinstance(raw, str):
        return raw[:1000]
    if isinstance(raw, dict):
        for key in ("message", "detail", "error"):
            value = raw.get(key)
            if value:
                return str(value)[:1000]
    return str(raw or "")[:1000]
