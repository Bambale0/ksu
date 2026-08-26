from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendDocument, SendVideo
from aiogram.types import FSInputFile

from app.services.media_assets import DownloadedMedia, MediaIngestService
from app.services.telegram_generation_media import send_generation_result_media


class FakeSession:
    def __init__(self, asset: object | None = None) -> None:
        self.asset = asset

    async def scalar(self, _statement: object) -> object | None:
        return self.asset


class FakeMessage:
    message_id = 77


def bad_video(message: str = "failed to get HTTP URL content") -> TelegramBadRequest:
    return TelegramBadRequest(method=SendVideo(chat_id=1, video="https://example.com/video.mp4"), message=message)


def bad_document(message: str = "document upload failed") -> TelegramBadRequest:
    return TelegramBadRequest(
        method=SendDocument(chat_id=1, document="https://example.com/video.mp4"),
        message=message,
    )


class FallbackBot:
    def __init__(self, *, fail_local_native: bool = False, fail_document: bool = False) -> None:
        self.fail_local_native = fail_local_native
        self.fail_document = fail_document
        self.video_calls: list[Any] = []
        self.document_calls: list[Any] = []

    async def send_video(self, **kwargs: Any) -> FakeMessage:
        video = kwargs["video"]
        self.video_calls.append(video)
        if isinstance(video, str):
            raise bad_video()
        if self.fail_local_native:
            raise bad_video("wrong type of the web page content")
        return FakeMessage()

    async def send_document(self, **kwargs: Any) -> FakeMessage:
        document = kwargs["document"]
        self.document_calls.append(document)
        if self.fail_document:
            raise bad_document()
        return FakeMessage()

    async def send_audio(self, **kwargs: Any) -> FakeMessage:
        raise AssertionError(f"unexpected audio call: {kwargs}")

    async def send_photo(self, **kwargs: Any) -> FakeMessage:
        raise AssertionError(f"unexpected photo call: {kwargs}")


class DirectBot(FallbackBot):
    async def send_video(self, **kwargs: Any) -> FakeMessage:
        self.video_calls.append(kwargs["video"])
        return FakeMessage()


def generation() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), user_id=uuid4())


@pytest.mark.asyncio
async def test_video_remote_url_success_keeps_fast_path(monkeypatch: pytest.MonkeyPatch) -> None:
    async def must_not_download(_cls: type[MediaIngestService], _url: str) -> DownloadedMedia:
        raise AssertionError("local download must not run when Telegram accepts the URL")

    monkeypatch.setattr(MediaIngestService, "_download", classmethod(must_not_download))
    bot = DirectBot()

    message = await send_generation_result_media(
        bot,  # type: ignore[arg-type]
        session=FakeSession(),  # type: ignore[arg-type]
        chat_id=1,
        generation=generation(),  # type: ignore[arg-type]
        media_type="video",
        result_url="https://provider.example/result.mp4",
        caption="ready",
        reply_markup=None,
    )

    assert message.message_id == 77
    assert bot.video_calls == ["https://provider.example/result.mp4"]
    assert bot.document_calls == []


@pytest.mark.asyncio
async def test_video_remote_fetch_failure_uploads_original_bytes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "original.mp4"
    source.write_bytes(b"original-video-bytes")

    async def download(_cls: type[MediaIngestService], _url: str) -> DownloadedMedia:
        return DownloadedMedia(
            path=source,
            size_bytes=source.stat().st_size,
            sha256="a" * 64,
            content_type="video/mp4",
            suffix=".mp4",
        )

    monkeypatch.setattr(MediaIngestService, "_download", classmethod(download))
    bot = FallbackBot()

    message = await send_generation_result_media(
        bot,  # type: ignore[arg-type]
        session=FakeSession(),  # type: ignore[arg-type]
        chat_id=1,
        generation=generation(),  # type: ignore[arg-type]
        media_type="video",
        result_url="https://provider.example/result.mp4",
        caption="ready",
        reply_markup=None,
    )

    assert message.message_id == 77
    assert len(bot.video_calls) == 2
    assert isinstance(bot.video_calls[0], str)
    assert isinstance(bot.video_calls[1], FSInputFile)
    assert bot.document_calls == []
    assert not source.exists(), "temporary original must be removed after Telegram upload"


@pytest.mark.asyncio
async def test_video_native_upload_failure_sends_original_as_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mov"
    source.write_bytes(b"mov-original")

    async def download(_cls: type[MediaIngestService], _url: str) -> DownloadedMedia:
        return DownloadedMedia(
            path=source,
            size_bytes=source.stat().st_size,
            sha256="b" * 64,
            content_type="video/quicktime",
            suffix=".mov",
        )

    monkeypatch.setattr(MediaIngestService, "_download", classmethod(download))
    bot = FallbackBot(fail_local_native=True)

    message = await send_generation_result_media(
        bot,  # type: ignore[arg-type]
        session=FakeSession(),  # type: ignore[arg-type]
        chat_id=1,
        generation=generation(),  # type: ignore[arg-type]
        media_type="video",
        result_url="https://provider.example/result.mov",
        caption="ready",
        reply_markup=None,
    )

    assert message.message_id == 77
    assert len(bot.video_calls) == 2
    assert len(bot.document_calls) == 1
    assert isinstance(bot.document_calls[0], FSInputFile)
    assert bot.document_calls[0].filename.endswith(".mov")
    assert not source.exists()


@pytest.mark.asyncio
async def test_all_media_upload_failures_escape_for_outbox_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")

    async def download(_cls: type[MediaIngestService], _url: str) -> DownloadedMedia:
        return DownloadedMedia(
            path=source,
            size_bytes=source.stat().st_size,
            sha256="c" * 64,
            content_type="video/mp4",
            suffix=".mp4",
        )

    monkeypatch.setattr(MediaIngestService, "_download", classmethod(download))
    bot = FallbackBot(fail_local_native=True, fail_document=True)

    with pytest.raises(TelegramBadRequest, match="document upload failed"):
        await send_generation_result_media(
            bot,  # type: ignore[arg-type]
            session=FakeSession(),  # type: ignore[arg-type]
            chat_id=1,
            generation=generation(),  # type: ignore[arg-type]
            media_type="video",
            result_url="https://provider.example/result.mp4",
            caption="ready",
            reply_markup=None,
        )

    assert not source.exists()
