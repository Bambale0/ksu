from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from aiogram.types import FSInputFile

from app.db.models import Generation
from app.services.media_assets import MediaIngestService
from app.workers.notifications import _send_generation_success


class VideoDeliveryBot:
    def __init__(self) -> None:
        self.url_attempts = 0
        self.multipart_videos: list[FSInputFile] = []
        self.messages: list[str] = []

    async def send_video(
        self,
        *,
        chat_id: int,
        video,
        caption: str,
        reply_markup=None,
        supports_streaming: bool = False,
    ):
        if isinstance(video, str):
            self.url_attempts += 1
            return SimpleNamespace(message_id=991)
        assert isinstance(video, FSInputFile)
        self.multipart_videos.append(video)
        return SimpleNamespace(message_id=990)

    async def send_document(self, **kwargs):
        raise AssertionError("document fallback should not be needed for a valid mp4")

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None):
        self.messages.append(text)
        return SimpleNamespace(message_id=992)


@pytest.mark.asyncio
async def test_video_result_is_downloaded_and_uploaded_as_file_before_any_url_attempt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    result_url = "https://provider.example/generated-video.mp4"
    video_path = tmp_path / "generated-video.mp4"
    video_path.write_bytes(b"fake-mp4")

    async def fake_download(url: str):
        assert url == result_url
        return SimpleNamespace(
            path=video_path,
            size_bytes=video_path.stat().st_size,
            suffix=".mp4",
        )

    monkeypatch.setattr(MediaIngestService, "_download", staticmethod(fake_download))

    generation = Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="video",
        status="succeeded",
        prompt="clip",
        cost_rox=Decimal("30.00"),
        result_url=result_url,
        parameters={
            "_model_id": "kling-3.0",
            "_result_urls": [result_url],
        },
    )
    bot = VideoDeliveryBot()

    message = await _send_generation_success(
        bot,  # type: ignore[arg-type]
        chat_id=123456,
        generation=generation,
    )

    assert message.message_id == 990
    assert bot.url_attempts == 0, "video must be downloaded by our server before Telegram delivery"
    assert len(bot.multipart_videos) == 1
    assert bot.multipart_videos[0].filename.endswith(".mp4")
    assert bot.messages == []
    assert not video_path.exists(), "temporary provider download must be removed after Telegram upload"


@pytest.mark.asyncio
async def test_video_url_is_only_last_resort_when_server_download_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_url = "https://provider.example/generated-video.mp4"

    async def broken_download(url: str):
        assert url == result_url
        raise RuntimeError("provider unavailable from worker")

    monkeypatch.setattr(MediaIngestService, "_download", staticmethod(broken_download))

    generation = Generation(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        kind="video",
        status="succeeded",
        prompt="clip",
        cost_rox=Decimal("30.00"),
        result_url=result_url,
        parameters={
            "_model_id": "kling-3.0",
            "_result_urls": [result_url],
        },
    )
    bot = VideoDeliveryBot()

    message = await _send_generation_success(
        bot,  # type: ignore[arg-type]
        chat_id=123456,
        generation=generation,
    )

    assert message.message_id == 991
    assert bot.url_attempts == 1
    assert bot.multipart_videos == []
    assert bot.messages == []
