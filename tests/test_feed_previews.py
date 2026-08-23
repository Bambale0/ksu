from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image

from app.core.config import settings
from app.services.feed_previews import FeedPreviewService
from app.services.feed_static import FeedStaticStorage


def test_feed_image_gets_bounded_server_preview(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "feed"
    root.mkdir()
    monkeypatch.setenv("FEED_STATIC_ROOT", str(root))
    monkeypatch.setenv("FEED_STATIC_PUBLIC_PREFIX", "/uploads/feed")
    monkeypatch.setattr(settings, "public_base_url", "")

    source = root / f"{uuid.uuid4()}.png"
    Image.new("RGBA", (1600, 1000), (40, 70, 120, 120)).save(source, "PNG")
    media_url = f"/uploads/feed/{source.name}"

    preview_url = FeedPreviewService.preview_url_for(media_url)

    assert preview_url == f"/uploads/feed/thumbs/{source.stem}.jpg"
    preview_path = FeedStaticStorage.path_for_url(preview_url)
    assert preview_path is not None and preview_path.is_file()
    assert preview_path.stat().st_size <= FeedPreviewService.max_bytes()
    with Image.open(preview_path) as preview:
        preview.load()
        assert max(preview.size) <= 768
        assert preview.mode == "RGB"


def test_video_does_not_fake_an_image_preview(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "feed"
    root.mkdir()
    monkeypatch.setenv("FEED_STATIC_ROOT", str(root))
    monkeypatch.setenv("FEED_STATIC_PUBLIC_PREFIX", "/uploads/feed")
    video = root / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypisom0000roxy-video")

    assert FeedPreviewService.preview_url_for("/uploads/feed/clip.mp4") is None
