from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest

from app.api.v1.pinterest_repeat import (
    PinterestRepeatRequest,
    PinterestSceneAnalysis,
    _build,
)
from app.providers.kie_pinterest_analysis import (
    KiePinterestAnalysisClient,
    PinterestSceneAnalysisProviderError,
    PinterestSceneAnalysisProviderResult,
    _parse_json_object,
)
from app.services.pinterest_scene_analysis import (
    PinterestSceneAnalysisError,
    PinterestSceneAnalysisService,
)

ROOT = Path(__file__).resolve().parents[1]


def sample_analysis() -> PinterestSceneAnalysis:
    return PinterestSceneAnalysis(
        scene="woman standing beside a stone balcony in an Italian street",
        composition="vertical medium-full portrait, subject slightly right of center",
        camera="eye-level camera, natural portrait perspective",
        pose="weight on right leg, left knee relaxed, torso slightly rotated",
        lighting="soft warm daylight from camera-left",
        environment="warm stone walls and narrow European street",
        wardrobe="light fitted top with dark straight-leg trousers",
        expression="calm confidence, relaxed mouth",
        gaze="directly into camera",
        must_preserve=["hand placement", "head angle", "subject scale", "background geometry"],
    )


def test_scene_analysis_is_embedded_into_generation_recipe() -> None:
    payload = PinterestRepeatRequest(
        scene_reference_url="https://cdn.example.com/scene.jpg",
        identity_reference_urls=["https://cdn.example.com/me.jpg"],
        height_cm=165,
        weight_kg=55,
        scene_analysis=sample_analysis(),
    )

    recipe = _build(payload)

    assert "ANALYZED SCENE BLUEPRINT" in recipe.prompt
    assert "weight on right leg" in recipe.prompt
    assert "soft warm daylight" in recipe.prompt
    assert "calm confidence" in recipe.prompt
    assert "directly into camera" in recipe.prompt
    assert "hand placement; head angle; subject scale; background geometry" in recipe.prompt
    assert "Never use it to override PERSON_IDENTITY" in recipe.prompt


def test_scene_analysis_normalizer_rejects_missing_required_fields() -> None:
    with pytest.raises(PinterestSceneAnalysisError, match="camera"):
        PinterestSceneAnalysisService._normalize(
            {
                "scene": "scene",
                "composition": "composition",
            }
        )


def test_scene_analysis_normalizer_bounds_provider_output() -> None:
    raw = sample_analysis().model_dump()
    raw["scene"] = "x" * 1200
    raw["must_preserve"] = ["y" * 400 for _ in range(20)]

    normalized = PinterestSceneAnalysisService._normalize(raw)

    assert len(normalized["scene"]) == PinterestSceneAnalysisService.MAX_TEXT_LENGTH
    assert len(normalized["must_preserve"]) == PinterestSceneAnalysisService.MAX_PRESERVE_ITEMS
    assert all(
        len(item) <= PinterestSceneAnalysisService.MAX_PRESERVE_ITEM_LENGTH
        for item in normalized["must_preserve"]
    )


def test_kie_parser_accepts_openai_text_content_blocks() -> None:
    analysis = sample_analysis().model_dump()
    payload = _parse_json_object([{"type": "text", "text": json.dumps(analysis)}])

    assert payload["scene"] == analysis["scene"]
    assert payload["gaze"] == analysis["gaze"]


def test_kie_parser_recovers_json_wrapped_in_provider_text() -> None:
    analysis = sample_analysis().model_dump()
    payload = _parse_json_object(
        "Structured result follows:\n" + json.dumps(analysis) + "\nDone."
    )

    assert payload["composition"] == analysis["composition"]
    assert payload["must_preserve"] == analysis["must_preserve"]


@pytest.mark.asyncio
async def test_scene_analysis_retries_one_malformed_provider_response() -> None:
    class _FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        async def analyze(self, *, image_url: str) -> PinterestSceneAnalysisProviderResult:
            self.calls += 1
            if self.calls == 1:
                raise PinterestSceneAnalysisProviderError("provider returned no JSON object")
            return PinterestSceneAnalysisProviderResult(
                model="gemini-2.5-pro",
                payload=sample_analysis().model_dump(),
            )

    client = _FlakyClient()
    analysis, provider_result = await PinterestSceneAnalysisService._analyze_provider(
        client,  # type: ignore[arg-type]
        image_url="https://cdn.example.com/scene.jpg",
        user_id=uuid.uuid4(),
    )

    assert client.calls == 2
    assert analysis["pose"].startswith("weight on right leg")
    assert provider_result.model == "gemini-2.5-pro"


@pytest.mark.asyncio
async def test_kie_scene_analyzer_requests_structured_pose_expression_and_gaze() -> None:
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        observed.update(body)
        analysis = sample_analysis().model_dump()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(analysis)}}]},
            request=request,
        )

    async with httpx.AsyncClient(
        base_url="https://api.kie.test",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        client = KiePinterestAnalysisClient("test-key", client=http_client)
        result = await client.analyze(image_url="https://cdn.example.com/scene.jpg")
        await client.aclose()

    assert result.model == "gemini-2.5-pro"
    assert result.payload["pose"].startswith("weight on right leg")
    assert result.payload["expression"].startswith("calm confidence")
    assert result.payload["gaze"] == "directly into camera"
    response_schema = observed["response_format"]
    assert isinstance(response_schema, dict)
    properties = response_schema["json_schema"]["schema"]["properties"]
    assert "pose" in properties
    assert "expression" in properties
    assert "gaze" in properties


def test_pinterest_ai_analysis_is_wired_to_api_and_reference_ui() -> None:
    endpoint = (ROOT / "app/api/v1/pinterest_repeat.py").read_text(encoding="utf-8")
    api = (ROOT / "frontend/mini-app/lib/pinterest-repeat-api.ts").read_text(encoding="utf-8")
    page = (ROOT / "frontend/mini-app/app/pinterest-repeat/page.tsx").read_text(encoding="utf-8")

    assert '@router.post("/analyze")' in endpoint
    assert "PinterestSceneAnalysisService.analyze" in endpoint
    assert '"/api/v1/pinterest-repeat/analyze"' in api
    assert "pinterestRepeatApi.analyze(imageUrl)" in page
    assert "сцена, свет и поза считаны с референса" in page
    assert "эмоция: {analysis.expression}" in page
    assert "scene_analysis: analysis" in page
