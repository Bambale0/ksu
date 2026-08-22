from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.services.feed_static import FeedStaticStorage, FeedStaticStorageError


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\nroxy-static-feed"


def _mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypisom0000roxy-static-feed"


@pytest.mark.asyncio
async def test_existing_static_feed_url_is_reused(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "feed"
    root.mkdir()
    monkeypatch.setenv("FEED_STATIC_ROOT", str(root))
    monkeypatch.setenv("FEED_STATIC_PUBLIC_PREFIX", "/uploads/feed")
    media = root / "existing.png"
    media.write_bytes(_png())

    items = await FeedStaticStorage.persist_urls(
        ["/uploads/feed/existing.png"],
        generation_id=uuid.uuid4(),
    )

    assert len(items) == 1
    assert items[0].public_url == "/uploads/feed/existing.png"
    assert items[0].content_type == "image/png"
    assert items[0].size_bytes == len(_png())
    assert FeedStaticStorage.local_url_exists(items[0].public_url)


@pytest.mark.asyncio
async def test_external_video_is_moved_to_immutable_static_name(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "feed"
    root.mkdir()
    monkeypatch.setenv("FEED_STATIC_ROOT", str(root))
    monkeypatch.setenv("FEED_STATIC_PUBLIC_PREFIX", "/uploads/feed")
    generation_id = uuid.uuid4()

    async def fake_download(_cls, _url: str):  # type: ignore[no-untyped-def]
        path = root / ".incoming.part"
        data = _mp4()
        path.write_bytes(data)
        import hashlib

        return path, ".mp4", "video/mp4", len(data), hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(FeedStaticStorage, "_download_external", classmethod(fake_download))
    items = await FeedStaticStorage.persist_urls(
        ["https://provider.example/result.mp4"],
        generation_id=generation_id,
    )

    assert len(items) == 1
    item = items[0]
    assert item.public_url.startswith(f"/uploads/feed/{generation_id}-1-")
    assert item.public_url.endswith(".mp4")
    assert item.path.is_file()
    assert item.path.read_bytes() == _mp4()
    assert item.content_type == "video/mp4"
    assert FeedStaticStorage.media_view(item.public_url, ordinal=0)["storage"] == "static"


@pytest.mark.asyncio
async def test_static_persist_is_all_or_nothing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "feed"
    root.mkdir()
    monkeypatch.setenv("FEED_STATIC_ROOT", str(root))
    monkeypatch.setenv("FEED_STATIC_PUBLIC_PREFIX", "/uploads/feed")
    generation_id = uuid.uuid4()
    calls = 0

    async def fake_download(_cls, _url: str):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        if calls == 2:
            raise FeedStaticStorageError("second media failed")
        path = root / f".incoming-{calls}.part"
        data = _png()
        path.write_bytes(data)
        import hashlib

        return path, ".png", "image/png", len(data), hashlib.sha256(data).hexdigest()

    monkeypatch.setattr(FeedStaticStorage, "_download_external", classmethod(fake_download))

    with pytest.raises(FeedStaticStorageError):
        await FeedStaticStorage.persist_urls(
            ["https://provider.example/one.png", "https://provider.example/two.png"],
            generation_id=generation_id,
        )

    assert not list(root.glob(f"{generation_id}-*"))


def test_unknown_magic_bytes_are_rejected(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "feed"
    root.mkdir()
    monkeypatch.setenv("FEED_STATIC_ROOT", str(root))
    path = root / "bad.bin"
    path.write_bytes(b"not-media")

    with pytest.raises(FeedStaticStorageError):
        FeedStaticStorage._inspect_file(path)
