from __future__ import annotations

import hashlib
import io
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from app.core.config import settings
from app.services.feed import FeedService
from app.services.reference_previews import ReferencePreviewService
from app.services.reference_static import ReferenceStaticStorage


def _stored_reference(tmp_path: Path, monkeypatch) -> str:  # type: ignore[no-untyped-def]
    root = tmp_path / "refs"
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    monkeypatch.setattr(settings, "public_base_url", "")
    buffer = io.BytesIO()
    Image.new("RGB", (900, 700), (80, 100, 130)).save(buffer, "PNG")
    data = buffer.getvalue()
    url, _path, _size = ReferenceStaticStorage.persist_stream(
        io.BytesIO(data),
        user_id=uuid.uuid4(),
        kind="image",
        file_hash=hashlib.sha256(data).hexdigest(),
        filename="reference.png",
        content_type="image/png",
        expected_size=len(data),
    )
    return url


def test_feed_reference_extractor_accepts_durable_roxy_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    url = _stored_reference(tmp_path, monkeypatch)
    generation = SimpleNamespace(
        parameters={"reference_image_urls": [url]},
        input_url=None,
    )

    images, videos = FeedService._references(generation)

    assert images == [url]
    assert videos == []


def test_reference_thumbnail_is_small_and_product_owned(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    url = _stored_reference(tmp_path, monkeypatch)

    thumb = ReferencePreviewService.thumbnail_path(url)

    assert thumb is not None and thumb.is_file()
    with Image.open(thumb) as image:
        image.load()
        assert max(image.size) <= 320
        assert image.format == "WEBP"


@pytest.mark.parametrize("extension", [".mp4", ".mpeg", ".ogv", ".avi", ".mkv"])
def test_video_preview_thumbnail_is_small_webp(tmp_path: Path, monkeypatch, extension: str) -> None:  # type: ignore[no-untyped-def]
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg unavailable")
    root = tmp_path / "refs"
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    source = root / "video" / f"example_{extension[1:]}{extension}"
    source.parent.mkdir(parents=True)
    encoded = root / "video" / "encoded.mp4"
    subprocess.run(
        [ffmpeg, "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=1",
         "-frames:v", "1", "-pix_fmt", "yuv420p", str(encoded)],
        check=True, capture_output=True, timeout=10,
    )
    source.write_bytes(encoded.read_bytes())

    thumb = ReferencePreviewService.thumbnail_path(f"/uploads/refs/video/{source.name}")

    assert thumb is not None and thumb.is_file()
    with Image.open(thumb) as image:
        assert image.format == "WEBP"
        assert max(image.size) <= 320
    assert thumb.stat().st_size < source.stat().st_size


def test_oversized_image_fails_closed_without_500(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    url = _stored_reference(tmp_path, monkeypatch)

    def bomb(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise Image.DecompressionBombError("oversized")

    monkeypatch.setattr(Image, "open", bomb)
    assert ReferencePreviewService.thumbnail_path(url) is None


def test_cold_thumbnail_jobs_are_bounded_and_coalesced(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "refs"
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(root))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    sources = [root / "image" / f"bounded-{index}.png" for index in range(3)]
    for source in sources:
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"test")
    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []
    lock = threading.Lock()

    def generate(_cls, url: str) -> None:  # type: ignore[no-untyped-def]
        with lock:
            calls.append(url)
            if len(calls) == 2:
                entered.set()
        release.wait(timeout=3)
        return None

    monkeypatch.setattr(ReferencePreviewService, "thumbnail_path", classmethod(generate))
    urls = [f"/uploads/refs/image/{source.name}" for source in sources]
    try:
        assert ReferencePreviewService.cached_or_schedule(urls[0]) is None
        assert ReferencePreviewService.cached_or_schedule(urls[0]) is None
        assert ReferencePreviewService.cached_or_schedule(urls[1]) is None
        assert entered.wait(timeout=2)
        assert ReferencePreviewService.cached_or_schedule(urls[2]) is None
        assert len(calls) == 2
    finally:
        release.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        ReferencePreviewService.cached_or_schedule(urls[2])
        if len(calls) == 3:
            break
        time.sleep(0.01)
    assert len(calls) == 3
