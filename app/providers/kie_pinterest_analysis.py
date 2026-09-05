from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


class PinterestSceneAnalysisProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PinterestSceneAnalysisProviderResult:
    model: str
    payload: dict[str, Any]


_PINTEREST_REPEAT_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "pinterest_repeat_scene_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "scene": {"type": "string"},
                "composition": {"type": "string"},
                "camera": {"type": "string"},
                "pose": {"type": "string"},
                "lighting": {"type": "string"},
                "environment": {"type": "string"},
                "wardrobe": {"type": "string"},
                "expression": {"type": "string"},
                "gaze": {"type": "string"},
                "must_preserve": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "scene",
                "composition",
                "camera",
                "pose",
                "lighting",
                "environment",
                "wardrobe",
                "expression",
                "gaze",
                "must_preserve",
            ],
            "additionalProperties": False,
        },
    },
}

_SYSTEM = (
    "You are a visual continuity analyst for reference-based image generation. "
    "Inspect only observable visual properties of the supplied reference image. "
    "Describe the scene, composition, camera/framing, body pose, lighting, environment, wardrobe, "
    "facial expression and gaze direction so another image model can recreate the same photograph. "
    "Do not identify the person, infer identity, ethnicity, health, religion, politics, sexuality, "
    "or other sensitive traits. Do not add facts that are not visually supported. "
    "Return concise English values in the required JSON schema. For a field that is not visible, "
    "use 'not clearly visible'. must_preserve must contain only the highest-value visual constraints."
)

_USER = (
    "Analyze this image as the SCENE_REFERENCE for a photo-repeat workflow. Prioritize exact pose, "
    "limb placement, head direction, subject scale/position, crop, perspective, camera height, "
    "lighting direction/softness, background geometry, clothing silhouette/palette, expression and gaze."
)


class KiePinterestAnalysisClient:
    MODEL = "gemini-2.5-pro"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.kie.ai",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key and client is None:
            raise PinterestSceneAnalysisProviderError("KIE_API_KEY is not configured")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(90.0, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def analyze(self, *, image_url: str) -> PinterestSceneAnalysisProviderResult:
        body = {
            "model": self.MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _USER},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
            "response_format": _PINTEREST_REPEAT_ANALYSIS_SCHEMA,
        }
        try:
            response = await self._client.post("/gemini-2.5-pro/v1/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content"))
            payload = _parse_json_object(content)
            return PinterestSceneAnalysisProviderResult(model=self.MODEL, payload=payload)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise PinterestSceneAnalysisProviderError(
                f"Pinterest scene analysis provider failed: {exc}"
            ) from exc


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError("Provider returned no JSON object")
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Provider JSON must be an object")
    return parsed
