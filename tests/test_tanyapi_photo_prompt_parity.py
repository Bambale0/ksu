from __future__ import annotations

import hashlib
import io
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.providers.kie_prompt_tools import KiePromptToolsClient, PromptToolProviderResult
from app.core.config import settings
from app.services.photo_analysis_media import image_source_to_analysis_input
from app.services.prompt_tools import ClaimedPromptTool, PromptToolProcessor, PromptToolService
from app.services.reference_static import ReferenceStaticStorage


def _persist_png(monkeypatch: pytest.MonkeyPatch, tmp_path) -> str:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    raw = io.BytesIO()
    Image.new("RGBA", (3200, 1200), (255, 0, 0, 128)).save(raw, format="PNG")
    data = raw.getvalue()
    stream = io.BytesIO(data)
    url, _path, _size = ReferenceStaticStorage.persist_stream(
        stream,
        user_id=uuid.uuid4(),
        kind="image",
        file_hash=hashlib.sha256(data).hexdigest(),
        filename="photo.png",
        content_type="image/png",
        expected_size=len(data),
    )
    return url


def _persist_video(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[str, bytes]:
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    data = b"\x00\x00\x00\x18ftypmp42roxy-video-reference"
    url, _path, _size = ReferenceStaticStorage.persist_stream(
        io.BytesIO(data),
        user_id=uuid.uuid4(),
        kind="video",
        file_hash=hashlib.sha256(data).hexdigest(),
        filename="clip.mp4",
        content_type="video/mp4",
        expected_size=len(data),
    )
    return url, data


def test_photo_analysis_converts_durable_reference_to_bounded_jpeg_data_uri(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    url = _persist_png(monkeypatch, tmp_path)
    prepared = image_source_to_analysis_input(url)
    assert prepared is not None
    assert prepared.startswith("data:image/jpeg;base64,")
    assert url not in prepared


def test_prompt_tool_accepts_roxy_owned_photo_reference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    url = _persist_png(monkeypatch, tmp_path)
    clean = PromptToolService._normalize_input(
        "prompt_builder",
        {"text": "Сделай такой же свет", "image_url": url},
    )
    # Durable URL remains the task source of truth; conversion is JIT in the provider adapter.
    assert clean["image_url"] == url


@pytest.mark.asyncio
async def test_image_prompt_uses_tanyapi_chain_and_never_sends_local_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    url = _persist_png(monkeypatch, tmp_path)
    provider = AsyncMock(
        return_value=PromptToolProviderResult(
            model="gpt-5-4",
            payload={"prompt_ru": "RU", "prompt_en": "EN"},
        )
    )
    monkeypatch.setattr("app.services.tanyapi_prompt_contract.build_photo_prompt", provider)

    client = KiePromptToolsClient("test-key", "https://api.kie.ai")
    try:
        result = await client.build_prompt(text="сохрани композицию", image_url=url)
    finally:
        await client.aclose()

    assert result.model == "gpt-5-4"
    kwargs = provider.await_args.kwargs
    assert kwargs["instruction"] == "сохрани композицию"
    assert kwargs["image_url"].startswith("data:image/jpeg;base64,")
    assert url not in kwargs["image_url"]


@pytest.mark.asyncio
async def test_video_prompt_uploads_roxy_owned_reference_before_kie_submission(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    url, data = _persist_video(monkeypatch, tmp_path)
    monkeypatch.setattr(settings, "kie_api_key", "test-key")
    uploads: list[bytes] = []
    seen: dict[str, object] = {}

    class FakeUploadClient:
        def __init__(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        async def upload_stream(self, *, file_name, content_type, stream, upload_path):  # type: ignore[no-untyped-def]
            seen.update(
                file_name=file_name,
                content_type=content_type,
                upload_path=upload_path,
            )
            uploads.append(stream.read())
            return SimpleNamespace(url="https://kie.example/runtime/clip.mp4")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("app.services.provider_media_transport.KieUploadClient", FakeUploadClient)
    class FakePromptClient:
        def __init__(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        async def aclose(self) -> None:
            return None

        async def build_video_prompt(self, **kwargs) -> PromptToolProviderResult:  # type: ignore[no-untyped-def]
            assert kwargs["video_url"] == "https://kie.example/runtime/clip.mp4"
            assert url not in kwargs["video_url"]
            assert kwargs["instruction"] == "motion"
            assert kwargs["duration_seconds"] == 5
            return PromptToolProviderResult(
                model="gemini-2.5-pro",
                payload={"prompt": "video prompt"},
                credits_consumed=Decimal("0.25"),
            )

    task_id = uuid.uuid4()
    task = SimpleNamespace(
        tool="video_prompt",
        input_payload={"video_url": url, "instruction": "motion", "duration_seconds": 5},
    )

    class FakeSession:
        async def get(self, *_args):  # type: ignore[no-untyped-def]
            return task

        async def rollback(self) -> None:
            raise AssertionError("rollback is not expected")

    complete = AsyncMock()
    monkeypatch.setattr("app.services.prompt_tools.KiePromptToolsClient", FakePromptClient)
    monkeypatch.setattr("app.services.prompt_tools.PromptToolOutboxService.complete", complete)
    monkeypatch.setattr(
        "app.services.prompt_tools.AbuseProtectionService.provider_submission_gate",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.prompt_tools.AbuseProtectionService.record_provider_success",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.prompt_tools.AbuseProtectionService.record_provider_failure",
        AsyncMock(),
    )

    await PromptToolProcessor.process(
        FakeSession(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        ClaimedPromptTool(outbox_id=uuid.uuid4(), task_id=task_id, attempts=1),
    )

    complete.assert_awaited_once()
    assert complete.await_args.kwargs["result"] == {"prompt": "video prompt"}
    assert complete.await_args.kwargs["model"] == "gemini-2.5-pro"
    assert uploads == [data]
    assert seen["content_type"] == "video/mp4"
    assert seen["upload_path"] == "ksu/runtime-inputs"
