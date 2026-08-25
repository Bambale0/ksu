from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.db.models import Generation
from app.providers.kie import KieClient
from app.services.generation_provider import GenerationProviderService
from app.services.model_catalog import ModelCatalog
from app.services.model_ui_contract import build_public_model_ui_schema

ROOT = Path(__file__).resolve().parents[1]
SEEDANCE_IDS = (
    "seedance-2.0",
    "seedance-2.0-fast",
    "seedance-2.0-mini",
    "seedance-2.5",
)


def test_mobile_keyboard_hides_fixed_navigation_and_allows_same_file_retry() -> None:
    layout = (ROOT / "frontend/mini-app/app/layout.tsx").read_text(encoding="utf-8")
    css = (ROOT / "frontend/mini-app/app/keyboard-ux.css").read_text(encoding="utf-8")
    script = (ROOT / "frontend/mini-app/public/keyboard-reference-ux.js").read_text(encoding="utf-8")

    assert 'import "./keyboard-ux.css"' in layout
    assert 'src="/mini-app/keyboard-reference-ux.js"' in layout
    assert "body.roxy-keyboard-open .bottom-nav" in css
    assert "textarea:focus" in css
    assert 'input.type !== "file"' in script
    assert 'input.value = ""' in script
    assert "visualViewport" in script


def test_all_seedance_reference_scenarios_are_explicitly_required() -> None:
    for model_id in SEEDANCE_IDS:
        schema = build_public_model_ui_schema(ModelCatalog.get(model_id).public_dict())
        scenarios = {item["id"]: item for item in schema["scenario"]["items"]}

        assert scenarios["first_frame"]["title"] == "Фото-референсы"
        assert scenarios["first_frame"]["visible_fields"] == ["reference_image_urls"]
        assert scenarios["first_frame"]["required_fields"] == ["reference_image_urls"]
        assert "first_frame_url" in scenarios["first_frame"]["clear_fields"]
        assert "last_frame_url" in scenarios["first_frame"]["clear_fields"]
        assert scenarios["first_last"]["required_fields"] == [
            "first_frame_url",
            "last_frame_url",
        ]
        assert scenarios["references"]["required_any"] == [
            "reference_image_urls",
            "reference_video_urls",
            "reference_audio_urls",
        ]


def test_generation_provider_keeps_seedance_first_frame_url() -> None:
    reference = "https://cdn.example/reference.png"
    generation = Generation(
        kind="multimodal_video",
        status="queued",
        prompt="make the subject wave",
        parameters={
            "prompt": "make the subject wave",
            "first_frame_url": reference,
            "duration": 5,
            "resolution": "720p",
            "aspect_ratio": "16:9",
            "_model_id": "seedance-2.0",
            "_provider_model": "bytedance/seedance-2",
        },
    )

    payload = GenerationProviderService._input_for(generation)
    assert payload["first_frame_url"] == reference
    assert "image_url" not in payload


@pytest.mark.asyncio
async def test_seedance_reference_reaches_kie_create_task_unchanged() -> None:
    reference = "https://cdn.example/reference.png"
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"data": {"taskId": "seedance-ref-task"}})

    client = KieClient("test-key", "https://api.kie.test")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        base_url="https://api.kie.test",
        transport=httpx.MockTransport(handler),
    )
    try:
        task_id = await client.create_task(
            model="bytedance/seedance-2",
            input_data={
                "prompt": "make the subject wave",
                "first_frame_url": reference,
                "duration": 5,
                "resolution": "720p",
                "aspect_ratio": "16:9",
            },
        )
    finally:
        await client.aclose()

    assert task_id == "seedance-ref-task"
    assert captured["model"] == "bytedance/seedance-2"
    assert isinstance(captured["input"], dict)
    assert captured["input"]["first_frame_url"] == reference
