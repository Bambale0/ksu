from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendVideo
from aiogram.types import FSInputFile

from app.db.models import Generation
from app.services.media_assets import MediaIngestService
from app.workers.notifications import _send_generation_success


class VideoFallbackBot:
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
            raise TelegramBadRequest(
                method=SendVideo(chat_id=chat_id, video=video),
                message="failed to get HTTP URL content",
            )
        assert isinstance(video, FSInputFile)
        self.multipart_videos.append(video)
        return SimpleNamespace(message_id=990)

    async def send_document(self, **kwargs):
        raise AssertionError("document fallback should not be needed for a valid mp4")

    async def send_message(self, *, chat_id: int, text: str, reply_markup=None):
        self.messages.append(text)
        return SimpleNamespace(message_id=991)


@pytest.mark.asyncio
async def test_video_result_is_uploaded_from_server_when_telegram_rejects_provider_url(
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
    bot = VideoFallbackBot()

    message = await _send_generation_success(
        bot,  # type: ignore[arg-type]
        chat_id=123456,
        generation=generation,
    )

    assert message.message_id == 990
    assert bot.url_attempts == 1
    assert len(bot.multipart_videos) == 1
    assert bot.multipart_videos[0].filename.endswith(".mp4")
    assert bot.messages == []
    assert not video_path.exists(), "temporary provider download must be removed after Telegram upload"
