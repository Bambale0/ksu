from __future__ import annotations

import httpx

from app.providers.kie_pinterest_analysis import (
    PinterestSceneAnalysisProviderError,
    PinterestSceneAnalysisProviderResult,
    _SYSTEM,
    _USER,
    _parse_json_object,
)
from app.providers.nexus_prompt_tools import (
    NEXUS_VISION_MODEL,
    _chat_content,
    _public_https_media_url,
)

_SCHEMA_HINT = """
Return one JSON object with exactly these fields:
scene, composition, camera, pose, lighting, environment, wardrobe,
expression, gaze, must_preserve.
All fields except must_preserve are strings. must_preserve is an array of strings.
Do not wrap JSON in markdown.
""".strip()


class NexusPinterestAnalysisClient:
    MODEL = NEXUS_VISION_MODEL

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://nexusapi.dev",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key and client is None:
            raise PinterestSceneAnalysisProviderError("NEXUS_API_KEY is not configured")
        self._owns_client = client is None
        self._authorization = f"Bearer {clean_key}"
        self._client = client or httpx.AsyncClient(
            base_url=str(base_url or "").rstrip("/"),
            timeout=httpx.Timeout(90.0, connect=10.0),
            headers={"Authorization": self._authorization},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def analyze(self, *, image_url: str) -> PinterestSceneAnalysisProviderResult:
        public_url = _public_https_media_url(image_url)
        body = {
            "model": self.MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": f"{_SYSTEM}\n\n{_SCHEMA_HINT}"},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _USER},
                        {"type": "image_url", "image_url": {"url": public_url}},
                    ],
                },
            ],
            "reasoning_effort": "high",
            "max_completion_tokens": 2048,
        }
        try:
            response = await self._client.post(
                "/v1/chat/completions",
                headers={"Authorization": self._authorization},
                json=body,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Provider returned a non-object response")
            payload = _parse_json_object(_chat_content(data))
            return PinterestSceneAnalysisProviderResult(
                model=self.MODEL,
                payload=payload,
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise PinterestSceneAnalysisProviderError(
                f"{self.MODEL} Pinterest scene analysis provider failed: {exc}"
            ) from exc
