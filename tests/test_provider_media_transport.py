from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.feed_static import FeedStaticStorage
from app.services.provider_media_transport import (
    ProviderMediaTransport,
    ProviderMediaTransportPermanentError,
)
from app.services.reference_static import ReferenceStaticStorage


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\nroxy-provider-transport"


def _reference_url(tmp_path: Path, monkeypatch) -> str:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    monkeypatch.setattr(settings, "public_base_url", "")
    data = _png()
    url, _path, _size = ReferenceStaticStorage.persist_stream(
        io.BytesIO(data),
        user_id=uuid.uuid4(),
        kind="image",
        file_hash=hashlib.sha256(data).hexdigest(),
        filename="ref.png",
        content_type="image/png",
        expected_size=len(data),
    )
    return url


@pytest.mark.asyncio
async def test_local_reference_is_uploaded_only_for_provider_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    local_url = _reference_url(tmp_path, monkeypatch)
    monkeypatch.setattr(settings, "kie_api_key", "test-key")
    uploads: list[tuple[str, bytes]] = []

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        async def upload_stream(self, *, file_name, content_type, stream, upload_path):  # type: ignore[no-untyped-def]
            uploads.append((file_name, stream.read()))
            assert content_type == "image/png"
            assert upload_path == "ksu/runtime-inputs"
            return SimpleNamespace(url="https://kie.example/runtime/ref.png")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.services.provider_media_transport.KieUploadClient",
        FakeClient,
    )

    original = {
        "image_urls": [local_url, local_url],
        "prompt": "portrait",
        "external": "https://cdn.example/keep.png",
    }
    prepared = await ProviderMediaTransport.prepare(original)

    assert original["image_urls"] == [local_url, local_url]
    assert prepared["image_urls"] == [
        "https://kie.example/runtime/ref.png",
        "https://kie.example/runtime/ref.png",
    ]
    assert prepared["external"] == "https://cdn.example/keep.png"
    assert len(uploads) == 1
    assert uploads[0][1] == _png()


@pytest.mark.asyncio
async def test_external_provider_payload_is_left_untouched_without_kie_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(settings, "kie_api_key", "")
    payload = {
        "image_url": "https://cdn.example/reference.png",
        "prompt": "keep external input",
    }

    prepared = await ProviderMediaTransport.prepare(payload)

    assert prepared is payload


@pytest.mark.asyncio
async def test_feed_static_media_can_be_reused_as_generation_input(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    feed_root = tmp_path / "feed"
    feed_root.mkdir()
    monkeypatch.setenv("FEED_STATIC_ROOT", str(feed_root))
    monkeypatch.setenv("FEED_STATIC_PUBLIC_PREFIX", "/uploads/feed")
    monkeypatch.setattr(settings, "kie_api_key", "test-key")
    media = feed_root / "published.png"
    media.write_bytes(_png())
    calls = 0

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
            pass

        async def upload_stream(self, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            assert kwargs["stream"].read() == _png()
            return SimpleNamespace(url="https://kie.example/runtime/feed.png")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        "app.services.provider_media_transport.KieUploadClient",
        FakeClient,
    )

    prepared = await ProviderMediaTransport.prepare(
        {"image_url": "/uploads/feed/published.png"}
    )

    assert prepared["image_url"] == "https://kie.example/runtime/feed.png"
    assert calls == 1
    assert FeedStaticStorage.local_url_exists("/uploads/feed/published.png")


@pytest.mark.asyncio
async def test_missing_local_reference_fails_before_provider_task(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REFERENCE_STATIC_ROOT", str(tmp_path / "refs"))
    monkeypatch.setenv("REFERENCE_STATIC_PUBLIC_PREFIX", "/uploads/refs")
    monkeypatch.setattr(settings, "kie_api_key", "test-key")

    with pytest.raises(ProviderMediaTransportPermanentError):
        await ProviderMediaTransport.prepare(
            {"image_url": "/uploads/refs/image/missing.png"}
        )
