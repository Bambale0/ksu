from __future__ import annotations

import pytest

from app.providers.kie import KieClient, KieProviderError
from app.services.model_routing import resolve_model_request
from app.services.seedance_reference_modes import enforce_seedance_reference_mode


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _PostClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.last_json: dict[str, object] | None = None

    async def post(self, _path: str, *, json: dict[str, object]) -> _Response:
        self.last_json = json
        return _Response(self.payload)


@pytest.mark.asyncio
async def test_kie_market_create_task_rejects_non_success_code() -> None:
    client = KieClient.__new__(KieClient)
    client._client = _PostClient({"code": 500, "msg": "bad input", "data": {}})

    with pytest.raises(KieProviderError, match="bad input"):
        await client.create_task(model="google/nano-banana", input_data={"prompt": "x"})


@pytest.mark.asyncio
async def test_seedance_provider_payload_uses_pure_reference_mode() -> None:
    fake = _PostClient({"code": 200, "msg": "success", "data": {"taskId": "task_123"}})
    client = KieClient.__new__(KieClient)
    client._client = fake

    task_id = await client.create_task(
        model="bytedance/seedance-2",
        input_data={
            "prompt": "keep the three people consistent",
            "first_frame_url": "https://example.com/first.png",
            "last_frame_url": "https://example.com/last.png",
            "reference_image_urls": ["https://example.com/person-1.png"],
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
    )

    assert task_id == "task_123"
    assert fake.last_json is not None
    provider_input = fake.last_json["input"]
    assert isinstance(provider_input, dict)
    assert provider_input["reference_image_urls"] == ["https://example.com/person-1.png"]
    assert "first_frame_url" not in provider_input
    assert "last_frame_url" not in provider_input


def test_seedance_router_folds_frame_fields_into_multirefs() -> None:
    routed = resolve_model_request(
        "seedance-2.0",
        {
            "prompt": "x",
            "first_frame_url": "https://example.com/first.png",
            "last_frame_url": "https://example.com/last.png",
            "reference_image_urls": ["https://example.com/ref.png"],
            "duration": 10,
            "resolution": "720p",
            "aspect_ratio": "16:9",
        },
    )

    assert routed.parameters["reference_image_urls"] == [
        "https://example.com/ref.png",
        "https://example.com/first.png",
        "https://example.com/last.png",
    ]
    assert "first_frame_url" not in routed.parameters
    assert "last_frame_url" not in routed.parameters


@pytest.mark.asyncio
async def test_suno_custom_mode_always_reaches_provider_with_title() -> None:
    fake = _PostClient({"code": 200, "msg": "success", "data": {"taskId": "music_123"}})
    client = KieClient.__new__(KieClient)
    client._client = fake

    task_id = await client.create_music_task(
        model="V5_5",
        input_data={
            "customMode": True,
            "instrumental": True,
            "style": "cinematic ambient",
        },
    )

    assert task_id == "music_123"
    assert fake.last_json is not None
    assert fake.last_json["title"] == "ROXY Track"
    assert fake.last_json["model"] == "V5_5"


def test_seedance_reference_mode_mutates_legacy_mixed_payload_to_documented_mode() -> None:
    payload = {
        "first_frame_url": "https://example.com/first.png",
        "last_frame_url": "https://example.com/last.png",
        "reference_video_urls": ["https://example.com/ref.mp4"],
    }

    enforce_seedance_reference_mode("bytedance/seedance-2", payload)

    assert payload == {"reference_video_urls": ["https://example.com/ref.mp4"]}
