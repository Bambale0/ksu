from __future__ import annotations

import httpx

from app.providers.kie_pinterest_quality import (
    PinterestQualityProviderError,
    PinterestQualityProviderResult,
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
scene_match_score, identity_match_score, pose_match_score,
composition_match_score, anatomy_ok, issues, retry_instruction.
Scores are integers 0..100, anatomy_ok is boolean, issues is an array of strings,
retry_instruction is a string. Do not wrap JSON in markdown.
""".strip()


class NexusPinterestQualityClient:
    MODEL = NEXUS_VISION_MODEL
    MAX_IDENTITY_IMAGES = 2

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://nexusapi.dev",
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        clean_key = str(api_key or "").strip()
        if not clean_key and client is None:
            raise PinterestQualityProviderError("NEXUS_API_KEY is not configured")
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

    async def evaluate(
        self,
        *,
        scene_url: str,
        identity_urls: list[str],
        candidate_url: str,
    ) -> PinterestQualityProviderResult:
        identities = [str(item).strip() for item in identity_urls if str(item).strip()]
        if len(identities) > self.MAX_IDENTITY_IMAGES:
            raise PinterestQualityProviderError(
                "Nexus quality gate supports at most 2 identity images"
            )

        content: list[dict[str, object]] = [
            {"type": "text", "text": _USER},
            {"type": "text", "text": "IMAGE 1 — SCENE_REFERENCE"},
            {
                "type": "image_url",
                "image_url": {"url": _public_https_media_url(scene_url)},
            },
            {
                "type": "text",
                "text": (
                    "IMAGES 2..N — PERSON_IDENTITY. All are the same supplied person; "
                    "use them only for visual identity consistency."
                ),
            },
        ]
        for identity_url in identities:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _public_https_media_url(identity_url)},
                }
            )
        content.extend(
            [
                {"type": "text", "text": "FINAL IMAGE — CANDIDATE"},
                {
                    "type": "image_url",
                    "image_url": {"url": _public_https_media_url(candidate_url)},
                },
            ]
        )

        body = {
            "model": self.MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": f"{_SYSTEM}\n\n{_SCHEMA_HINT}"},
                {"role": "user", "content": content},
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
            return PinterestQualityProviderResult(model=self.MODEL, payload=payload)
        except PinterestQualityProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise PinterestQualityProviderError(
                f"Nexus Pinterest quality provider failed: {exc}"
            ) from exc
