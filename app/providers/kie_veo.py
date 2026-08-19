from __future__ import annotations

from typing import Any

import httpx

from app.providers.kie import KieProviderError, KieTask
from app.services.kie_video_contracts import normalize_kie_veo_input


class KieVeoClient:
    """Adapter for Kie's dedicated Veo 3.1 API surface.

    Veo tasks do not use the Market /jobs/createTask endpoint, so keeping this
    adapter separate prevents accidental request-shape regressions in generic
    Market models.
    """

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
        input_data: dict[str, Any],
        callback_url: str = "",
    ) -> str:
        normalized = normalize_kie_veo_input(input_data)
        body: dict[str, Any] = {
            "prompt": str(normalized.get("prompt") or ""),
            "imageUrls": list(normalized.get("image_urls") or []),
            "model": str(normalized.get("veo_model") or "veo3_fast"),
            "aspect_ratio": str(normalized.get("aspect_ratio") or "16:9"),
            "enableFallback": bool(normalized.get("enable_fallback", False)),
            "enableTranslation": bool(normalized.get("enable_translation", True)),
            "generationType": str(normalized.get("generation_type") or "TEXT_2_VIDEO"),
        }
        watermark = str(normalized.get("watermark_text") or "").strip()
        if watermark:
            body["watermark"] = watermark
        if callback_url:
            body["callBackUrl"] = callback_url

        response = await self._client.post("/api/v1/veo/generate", json=body)
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 200:
            raise KieProviderError(f"Kie Veo generation rejected: {payload.get('msg') or payload!r}")
        task_id = (payload.get("data") or {}).get("taskId")
        if not task_id:
            raise KieProviderError(f"Kie Veo generation returned no taskId: {payload!r}")
        return str(task_id)

    async def get_task(self, task_id: str) -> KieTask:
        response = await self._client.get(
            "/api/v1/veo/record-info",
            params={"taskId": task_id},
        )
        response.raise_for_status()
        payload = response.json()
        if int(payload.get("code") or 0) != 200:
            raise KieProviderError(f"Kie Veo record-info failed: {payload.get('msg') or payload!r}")
        data = payload.get("data") or {}
        try:
            success_flag = int(data.get("successFlag") or 0)
        except (TypeError, ValueError):
            success_flag = 0
        if success_flag == 1:
            state = "success"
        elif success_flag in {2, 3}:
            state = "fail"
        else:
            state = "generating"
        provider_response = data.get("response") if isinstance(data.get("response"), dict) else {}
        result_urls = provider_response.get("resultUrls") or []
        if not isinstance(result_urls, list):
            result_urls = []
        return KieTask(
            task_id=str(data.get("taskId") or task_id),
            state=state,
            result_urls=[str(url) for url in result_urls if isinstance(url, str) and url],
            fail_code=str(data.get("errorCode") or ""),
            fail_message=str(data.get("errorMessage") or ""),
            raw=payload,
        )