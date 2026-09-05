from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


class PinterestQualityProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PinterestQualityProviderResult:
    model: str
    payload: dict[str, Any]


_PINTEREST_REPEAT_QUALITY_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "pinterest_repeat_quality_gate",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "scene_match_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "identity_match_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "pose_match_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "composition_match_score": {"type": "integer", "minimum": 0, "maximum": 100},
                "anatomy_ok": {"type": "boolean"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "retry_instruction": {"type": "string"},
            },
            "required": [
                "scene_match_score",
                "identity_match_score",
                "pose_match_score",
                "composition_match_score",
                "anatomy_ok",
                "issues",
                "retry_instruction",
            ],
            "additionalProperties": False,
        },
    },
}

_SYSTEM = (
    "You are a strict visual quality evaluator for a reference-based photo recreation workflow. "
    "Compare three roles: SCENE_REFERENCE defines scene, framing, camera, pose, light and composition; "
    "PERSON_IDENTITY images define only the visual appearance of the same supplied person; "
    "CANDIDATE is the generated output. Score only observable visual similarity. "
    "Do not identify any real person or infer sensitive traits. Do not reward copying the identity "
    "of a person visible in SCENE_REFERENCE. identity_match_score means visual consistency between "
    "CANDIDATE and PERSON_IDENTITY only. retry_instruction must be concise, actionable and must never "
    "request a different identity. Return the required JSON object only."
)

_USER = (
    "Evaluate whether CANDIDATE faithfully recreates SCENE_REFERENCE while keeping PERSON_IDENTITY. "
    "Be strict about head direction, limb placement, body rotation, crop, subject scale/position, "
    "camera perspective, background geometry and lighting. anatomy_ok is false for malformed hands, "
    "duplicated limbs/people, broken face geometry or other obvious anatomical defects."
)


class KiePinterestQualityClient:
    MODEL = "gemini-2.5-pro"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.kie.ai",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key and client is None:
            raise PinterestQualityProviderError("KIE_API_KEY is not configured")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(90.0, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def evaluate(
        self,
        *,
        scene_url: str,
        identity_urls: list[str],
        candidate_url: str,
    ) -> PinterestQualityProviderResult:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": _USER},
            {"type": "text", "text": "IMAGE 1 — SCENE_REFERENCE"},
            {"type": "image_url", "image_url": {"url": scene_url}},
            {
                "type": "text",
                "text": (
                    "IMAGES 2..N — PERSON_IDENTITY (all are the same supplied person; "
                    "use them only for visual identity consistency)"
                ),
            },
        ]
        for identity_url in identity_urls:
            content.append({"type": "image_url", "image_url": {"url": identity_url}})
        content.extend(
            [
                {"type": "text", "text": "FINAL IMAGE — CANDIDATE"},
                {"type": "image_url", "image_url": {"url": candidate_url}},
            ]
        )
        body = {
            "model": self.MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": content},
            ],
            "response_format": _PINTEREST_REPEAT_QUALITY_SCHEMA,
        }
        try:
            response = await self._client.post("/gemini-2.5-pro/v1/chat/completions", json=body)
            response.raise_for_status()
            data = response.json()
            message = ((data.get("choices") or [{}])[0].get("message") or {})
            payload = _parse_json_object(message.get("content"))
            return PinterestQualityProviderResult(model=self.MODEL, payload=payload)
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise PinterestQualityProviderError(
                f"Pinterest quality provider failed: {exc}"
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
