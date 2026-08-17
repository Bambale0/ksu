from __future__ import annotations

from typing import Any

import httpx

from app.providers.kie import KieTask


class HeyGenProviderError(RuntimeError):
    pass


class HeyGenClient:
    def __init__(self, api_key: str, base_url: str = "https://api.heygen.com") -> None:
        if not api_key:
            raise HeyGenProviderError("HEYGEN_API_KEY is not configured")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def create_task(self, *, input_data: dict[str, Any]) -> str:
        character: dict[str, Any] = {
            "type": "avatar",
            "avatar_id": str(input_data.get("avatar_id") or ""),
            "avatar_style": str(input_data.get("avatar_style") or "normal"),
        }
        voice: dict[str, Any] = {
            "type": "text",
            "input_text": str(input_data.get("input_text") or ""),
            "voice_id": str(input_data.get("voice_id") or ""),
        }
        if input_data.get("voice_speed") not in (None, ""):
            voice["speed"] = float(input_data["voice_speed"])
        if input_data.get("voice_pitch") not in (None, ""):
            voice["pitch"] = float(input_data["voice_pitch"])

        video_input: dict[str, Any] = {"character": character, "voice": voice}
        background_type = str(input_data.get("background_type") or "").strip()
        background_value = str(input_data.get("background_value") or "").strip()
        if background_type and background_value:
            background: dict[str, Any] = {"type": background_type}
            if background_type == "color":
                background["value"] = background_value
            else:
                background["url"] = background_value
            video_input["background"] = background

        body: dict[str, Any] = {"video_inputs": [video_input]}
        width = input_data.get("width")
        height = input_data.get("height")
        if width not in (None, "") and height not in (None, ""):
            body["dimension"] = {"width": int(width), "height": int(height)}
        if input_data.get("caption") not in (None, ""):
            body["caption"] = bool(input_data["caption"])
        title = str(input_data.get("title") or "").strip()
        if title:
            body["title"] = title

        response = await self._client.post("/v2/video/generate", json=body)
        response.raise_for_status()
        payload = response.json()
        video_id = (payload.get("data") or {}).get("video_id")
        if not video_id:
            raise HeyGenProviderError(
                f"HeyGen video generation returned no video_id: {payload!r}"
            )
        return str(video_id)

    async def get_task(self, video_id: str) -> KieTask:
        response = await self._client.get(
            "/v1/video_status.get",
            params={"video_id": video_id},
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        provider_status = str(data.get("status") or "pending").lower()
        if provider_status == "completed":
            state = "success"
        elif provider_status == "failed":
            state = "fail"
        else:
            state = "generating"
        result_url = str(data.get("video_url") or "")
        error = data.get("error")
        return KieTask(
            task_id=str(data.get("video_id") or video_id),
            state=state,
            result_urls=[result_url] if result_url else [],
            fail_code="HEYGEN_FAILED" if state == "fail" else "",
            fail_message=str(error or ""),
            raw=payload,
        )
