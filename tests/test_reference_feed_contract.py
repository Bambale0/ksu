from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

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
