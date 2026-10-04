from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.providers.nexus_prompt_tools import (
    NEXUS_VISION_MODEL,
    NexusPromptToolsClient,
    _published_prompt_frames,
)
from app.services.prompt_tools import _model_for_prompt_tool, _provider_for_prompt_tool


def test_all_new_prompt_media_routes_use_nexus() -> None:
    assert _provider_for_prompt_tool("image_analysis", {"image_url": "https://example.test/a.jpg"}) == "nexus"
    assert _provider_for_prompt_tool("prompt_builder", {"text": "portrait", "image_url": None}) == "nexus"
    assert _provider_for_prompt_tool(
        "prompt_builder",
        {"text": "match image", "image_url": "https://example.test/a.jpg"},
    ) == "nexus"
    assert _provider_for_prompt_tool("video_prompt", {"video_url": "https://example.test/a.mp4"}) == "nexus"

    assert _model_for_prompt_tool("image_analysis", {"image_url": "https://example.test/a.jpg"}) == NEXUS_VISION_MODEL
    assert _model_for_prompt_tool("prompt_builder", {"text": "portrait", "image_url": None}) == "gpt-5.5"
    assert _model_for_prompt_tool(
        "prompt_builder",
        {"text": "match image", "image_url": "https://example.test/a.jpg"},
    ) == NEXUS_VISION_MODEL
    assert _model_for_prompt_tool("video_prompt", {"video_url": "https://example.test/a.mp4"}) == NEXUS_VISION_MODEL


@pytest.mark.asyncio
async def test_nexus_image_prompt_uses_vision_model_and_public_image_url() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "prompt_ru": "Русский визуальный промпт",
                                    "prompt_en": "English visual prompt",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusPromptToolsClient("test-key", client=http_client)
        result = await client.build_prompt(
            text="сохрани свет",
            image_url="https://cdn.example.test/ref.jpg",
        )

    assert result.model == NEXUS_VISION_MODEL
    assert result.payload["prompt_ru"] == "Русский визуальный промпт"
    body = calls[0]
    assert body["model"] == NEXUS_VISION_MODEL
    content = body["messages"][1]["content"]
    assert content[0]["type"] == "text"
    assert content[1] == {
        "type": "image_url",
        "image_url": {"url": "https://cdn.example.test/ref.jpg"},
    }


def test_temporary_prompt_frames_are_public_and_removed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings

    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")

    paths: list[Path] = []
    with _published_prompt_frames([b"jpeg-one", b"jpeg-two"]) as urls:
        assert len(urls) == 2
        assert all(url.startswith("https://roxy.example/uploads/refs/prompt-frames/") for url in urls)
        root = tmp_path / "refs" / "prompt-frames"
        paths = list(root.rglob("*.jpg"))
        assert len(paths) == 2
        assert all(path.is_file() for path in paths)

    assert paths
    assert all(not path.exists() for path in paths)


@pytest.mark.asyncio
async def test_nexus_video_prompt_publishes_four_frames_then_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings

    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")

    async def fake_video_bytes(_url: str) -> bytes:
        return b"video-bytes"

    monkeypatch.setattr("app.providers.nexus_prompt_tools._video_bytes", fake_video_bytes)
    monkeypatch.setattr(
        "app.providers.nexus_prompt_tools.probe_video_duration_seconds",
        lambda _data: 8.0,
    )

    seen_max_frames: list[int] = []

    def fake_frames(
        _data: bytes,
        *,
        duration_seconds: float,
        max_frames: int,
    ) -> list[bytes]:
        assert duration_seconds == 8.0
        seen_max_frames.append(max_frames)
        return [f"jpeg-{index}".encode() for index in range(max_frames)]

    monkeypatch.setattr(
        "app.providers.nexus_prompt_tools._extract_frame_jpeg_bytes_sync",
        fake_frames,
    )

    frame_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        content = body["messages"][1]["content"]
        image_blocks = [item for item in content if item.get("type") == "image_url"]
        assert body["model"] == NEXUS_VISION_MODEL
        assert len(image_blocks) == 4
        for block in image_blocks:
            url = block["image_url"]["url"]
            frame_urls.append(url)
            relative = url.split("/uploads/refs/", 1)[1]
            assert (tmp_path / "refs" / relative).is_file()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "prompt_ru": "Русский видео-промпт",
                                    "prompt_en": "English video prompt",
                                    "timeline_ru": ["начало", "финал"],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://nexusapi.dev",
    ) as http_client:
        client = NexusPromptToolsClient("test-key", client=http_client)
        result = await client.build_video_prompt(
            video_url="https://roxy.example/uploads/refs/video/ref.mp4",
            instruction="сохрани движение",
            duration_seconds=5,
        )

    assert result.model == NEXUS_VISION_MODEL
    assert result.payload["prompt_ru"] == "Русский видео-промпт"
    assert seen_max_frames == [4]
    assert len(frame_urls) == 4
    assert not (tmp_path / "refs" / "prompt-frames").exists()


def test_external_ref_path_is_not_treated_as_owned_media(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from app.core.config import settings
    from app.providers.nexus_prompt_tools import _local_media_path, _public_https_media_url

    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setattr(settings, "public_base_url", "https://roxy.example")

    external = "https://evil.example/uploads/refs/image/same-path.jpg"
    assert _local_media_path(external) is None
    assert _public_https_media_url(external) == external


def test_stale_prompt_frame_cleanup_keeps_active_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import os
    import time

    from app.providers.nexus_prompt_tools import cleanup_stale_prompt_frames

    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    root = tmp_path / "refs" / "prompt-frames"
    stale = root / "stale"
    active = root / "active"
    stale.mkdir(parents=True)
    active.mkdir(parents=True)
    (stale / "frame.jpg").write_bytes(b"old")
    (active / "frame.jpg").write_bytes(b"new")
    old = time.time() - 3600
    os.utime(stale, (old, old))

    removed = cleanup_stale_prompt_frames(max_age_seconds=900)

    assert removed == 1
    assert not stale.exists()
    assert active.is_dir()
